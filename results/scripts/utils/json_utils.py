"""JSON file handling utilities.

This module provides shared functions for loading and parsing JSON files
used throughout the vLLM benchmark results processing pipeline.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Union


def load_json_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Load and parse JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_json_safe(
    file_path: Union[str, Path],
    default: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Load JSON file with safe fallback to default.

    This function catches common JSON loading errors and returns a default
    value instead of raising exceptions. Warnings are printed to stderr.

    Args:
        file_path: Path to JSON file
        default: Value to return on error (default: empty dict)

    Returns:
        Parsed JSON data or default value

    Examples:
        >>> data = load_json_safe("config.json")
        >>> data = load_json_safe("optional.json", default={"key": "value"})
    """
    if default is None:
        default = {}

    try:
        return load_json_file(file_path)
    except FileNotFoundError:
        print(f"Warning: JSON file not found: {file_path}", file=sys.stderr)
        return default
    except json.JSONDecodeError as e:
        print(
            f"Warning: Could not parse JSON from {file_path}: {e}",
            file=sys.stderr
        )
        return default
    except Exception as e:
        print(
            f"Warning: Unexpected error loading {file_path}: {e}",
            file=sys.stderr
        )
        return default
