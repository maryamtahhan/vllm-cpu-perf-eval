"""vLLM CPU Wrapper for MTEB.

This wrapper provides HTTP-based access to vLLM servers for MTEB benchmarks,
addressing limitations in MTEB's default vLLM wrapper.

Key Differences from MTEB's Default vllm_wrapper.py:

1. **HTTP Endpoint Support** - MTEB's default wrapper only supports
   local in-process vLLM instantiation via `vllm.LLM()`. This wrapper
   uses vLLM's OpenAI-compatible HTTP API (`/v1/embeddings`) to connect
   to running servers.

2. **Remote Server Testing** - Enables testing of:
   - Remote vLLM CPU servers
   - Remote vLLM GPU servers
   - Red Hat AI Inference Server (RHAIIS) endpoints
   - Any vLLM-compatible embedding endpoint

3. **No GPU Assumptions** - MTEB's default assumes GPU availability
   with `gpu_memory_utilization=0.9` and `tensor_parallel_size`
   parameters. This wrapper works with any backend (CPU or GPU) via HTTP.

4. **Reusable Server** - Tests can reuse a running vLLM server instead
   of loading model weights on every MTEB benchmark run, significantly
   reducing setup time and memory overhead.

5. **Enhanced Features**:
   - Auto-detection of max_length from model metadata
   - Automatic truncation via `truncate_prompt_tokens`
   - SSL verification control for testing environments
   - Enhanced retry logic and incomplete response validation

MTEB's Default Behavior:
    # MTEB's vllm_wrapper.py (local instantiation only)
    from vllm import LLM
    llm = LLM(model=model_name, gpu_memory_utilization=0.9)
    embeddings = llm.encode(texts)

This Wrapper's Approach:
    # HTTP-based wrapper (remote endpoints)
    wrapper = VllmCPUEncoderWrapper(
        endpoint_url="http://vllm-server:8000",
        model_name="RedHatAI/granite-embedding-english-r2"
    )
    # Calls /v1/embeddings HTTP API
    embeddings = wrapper.encode(dataloader, task_metadata=task)

Note: The "CPU" in the name is historical - this wrapper works with any
vLLM endpoint (CPU or GPU) via HTTP.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests

from mteb.models.abs_encoder import AbsEncoder
from mteb.types import PromptType

if TYPE_CHECKING:
    from collections.abc import Callable

    from torch.utils.data import DataLoader

    from mteb.abstasks.task_metadata import TaskMetadata
    from mteb.types import Array, BatchedInput

logger = logging.getLogger(__name__)


class VllmCPUEncoderWrapper(AbsEncoder):
    """vLLM CPU wrapper for MTEB embedding benchmarks.

    This wrapper uses the OpenAI-compatible HTTP API to communicate with
    a vLLM server (CPU backend) or RHAIIS instance.

    Args:
        endpoint_url: URL of the vLLM server (e.g., "http://localhost:8000")
        model_name: Name of the model loaded in vLLM
        api_key: Optional API key for authentication
        revision: The revision of the model to use
        prompt_dict: A dictionary mapping task names to prompt strings
        use_instructions: Whether to use instructions from the prompt_dict
        instruction_template: A template or callable to format instructions
        apply_instruction_to_documents: Whether to apply instructions
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for failed requests
        batch_size: Batch size for processing embeddings
        verify_ssl: Whether to verify SSL certificates (default: True)
    """

    def __init__(
        self,
        endpoint_url: str,
        model_name: str,
        api_key: str | None = None,
        revision: str | None = None,
        *,
        prompt_dict: dict[str, str] | None = None,
        use_instructions: bool = False,
        instruction_template: (
            str | Callable[[str, PromptType | None], str] | None
        ) = None,
        apply_instruction_to_documents: bool = True,
        timeout: int = 300,
        max_retries: int = 3,
        batch_size: int = 32,
        verify_ssl: bool = True,
        max_length: int | None = None,
    ):
        """Initialize the vLLM CPU wrapper.

        Args:
            max_length: Maximum sequence length. If provided, texts will be truncated
                       to this length before sending to vLLM. If None, uses model's
                       default (may cause errors for long inputs).
        """
        self.endpoint_url = endpoint_url.rstrip("/")
        self.api_key = api_key
        self.prompts_dict = prompt_dict
        self.use_instructions = use_instructions
        self.instruction_template = instruction_template
        self.apply_instruction_to_passages = apply_instruction_to_documents
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.verify_ssl = verify_ssl
        self.max_length = max_length

        # MTEB looks for these attributes directly for result organization
        self.model_name = model_name
        self.revision = revision if revision else "main"

        # Set MTEB model metadata for proper result organization
        # MTEB will construct mteb_model_meta from model_name and revision if not set
        self.mteb_model_meta = None

        if use_instructions and instruction_template is None:
            raise ValueError(
                "To use instructions, an instruction_template must be provided. "
                "For example, `Instruction: {instruction}`"
            )

        if (
            isinstance(instruction_template, str)
            and "{instruction}" not in instruction_template
        ):
            raise ValueError(
                "Instruction template must contain the string '{instruction}'."
            )

        # Verify server is reachable
        self._verify_server()

    def _verify_server(self) -> None:
        """Verify that the vLLM server is reachable and get model info."""
        try:
            response = requests.get(
                f"{self.endpoint_url}/v1/models",
                timeout=10,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            models = response.json()

            # Check if our model is available
            available_models = [m["id"] for m in models.get("data", [])]
            if self.model_name not in available_models:
                logger.warning(
                    f"Model '{self.model_name}' not found in server. "
                    f"Available models: {available_models}"
                )
                # Still allow initialization - model name might be alias
            else:
                logger.info(
                    f"Successfully connected to vLLM server. "
                    f"Model: {self.model_name}"
                )

                # Auto-detect max_length from model info if not provided
                if self.max_length is None:
                    for model in models.get("data", []):
                        if model["id"] == self.model_name:
                            # vLLM returns max_model_len in model metadata
                            max_model_len = model.get("max_model_len")
                            if max_model_len:
                                self.max_length = max_model_len
                                logger.info(
                                    f"Auto-detected max_length={self.max_length} "
                                    f"from model metadata"
                                )
                            break

        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to vLLM server at "
                f"{self.endpoint_url}: {e}"
            ) from e

    def _get_embeddings(self, texts: list[str]) -> Array:
        """Get embeddings from the vLLM server via HTTP API.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings
        """
        import numpy as np

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "input": texts,
            "encoding_format": "float",
        }

        # Add truncation parameter if max_length is set
        # This tells vLLM to truncate inputs to model's max length
        if self.max_length:
            payload["truncate_prompt_tokens"] = self.max_length

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.endpoint_url}/v1/embeddings",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                response.raise_for_status()

                result = response.json()

                # Extract embeddings in correct order
                embeddings = [None] * len(texts)
                for item in result["data"]:
                    embeddings[item["index"]] = item["embedding"]

                # Validate all embeddings were returned
                missing_indices = [i for i, emb in enumerate(embeddings) if emb is None]
                if missing_indices:
                    raise RuntimeError(
                        f"Incomplete embeddings from vLLM server: "
                        f"expected {len(texts)} embeddings, got {len(texts) - len(missing_indices)}. "
                        f"Missing indices: {missing_indices[:10]}"  # Show first 10
                    )

                # Convert to numpy array
                return np.array(embeddings, dtype=np.float32)

            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Request timeout "
                        f"(attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying..."
                    )
                    continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Request failed "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying..."
                    )
                    continue
                raise RuntimeError(
                    f"Failed to get embeddings from vLLM server: {e}"
                ) from e

    def encode(
        self,
        inputs: DataLoader[BatchedInput],
        *,
        task_metadata: TaskMetadata,
        hf_split: str,
        hf_subset: str,
        prompt_type: PromptType | None = None,
        **kwargs: Any,
    ) -> Array:
        """Encode the given sentences using the vLLM server.

        Args:
            inputs: The sentences to encode
            task_metadata: The metadata of the task
            prompt_type: The type of prompt (query or passage)
            hf_split: Split of current task
            hf_subset: Subset of current task
            **kwargs: Additional arguments

        Returns:
            The encoded sentences as embeddings
        """
        import numpy as np

        # Determine prompt to use
        prompt = ""
        if self.use_instructions and self.prompts_dict is not None:
            prompt = self.get_task_instruction(task_metadata, prompt_type)
        elif self.prompts_dict is not None:
            prompt_name = self.get_prompt_name(task_metadata, prompt_type)
            if prompt_name is not None:
                prompt = self.prompts_dict.get(prompt_name, "")

        # Skip instruction for documents if configured
        if (
            self.use_instructions
            and self.apply_instruction_to_passages is False
            and prompt_type == PromptType.document
        ):
            logger.info(
                f"No instruction used, because prompt type = {prompt_type}"
            )
            prompt = ""
        else:
            if prompt:
                logger.info(
                    f"Using instruction: '{prompt}' for task: '{task_metadata.name}' "
                    f"prompt type: '{prompt_type}'"
                )

        # Collect all texts from batches
        texts = [prompt + text for batch in inputs for text in batch["text"]]

        # Process in batches to avoid overwhelming the server
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i : i + self.batch_size]
            logger.debug(
                f"Processing batch {i // self.batch_size + 1} "
                f"({len(batch_texts)} texts)"
            )
            batch_embeddings = self._get_embeddings(batch_texts)
            all_embeddings.append(batch_embeddings)

        # Concatenate all batches
        embeddings = np.vstack(all_embeddings)
        return embeddings
