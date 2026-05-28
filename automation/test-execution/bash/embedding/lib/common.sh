#!/usr/bin/env bash
# Common functions for embedding model tests
# Source this file in embedding test scripts with: source "${SCRIPT_DIR}/lib/common.sh"

# Colors for output
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export NC='\033[0m' # No Color

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $*" >&2
    fi
}

# ============================================================================
# Unsupported Test Suite Guard
# ============================================================================

check_unsupported_guard() {
    local script_name="${1:-embedding test script}"

    if [[ "${ALLOW_UNSUPPORTED_TESTS:-false}" != "true" ]]; then
        echo -e "" >&2
        echo -e "${RED}❌ EMBEDDING MODELS TEST SUITE NOT YET SUPPORTED${NC}" >&2
        echo -e "" >&2
        echo -e "This script (${script_name}) is blocked because the Embedding Models test" >&2
        echo -e "suite is still work in progress and not validated for end users." >&2
        echo -e "" >&2
        echo -e "${GREEN}✅ USE SUPPORTED TESTS INSTEAD:${NC}" >&2
        echo -e "" >&2
        echo -e "Concurrent Load Testing (Phase 1 & Phase 2) is fully validated for LLM models." >&2
        echo -e "" >&2
        echo -e "  cd ${PROJECT_ROOT}/automation/test-execution/ansible" >&2
        echo -e "  ansible-playbook -i inventory/hosts.yml llm-benchmark-concurrent-load.yml \\" >&2
        echo -e "    -e \"test_model=TinyLlama/TinyLlama-1.1B-Chat-v1.0\" \\" >&2
        echo -e "    -e \"base_workload=chat\" \\" >&2
        echo -e "    -e \"core_sweep_counts=[16,32,64]\" \\" >&2
        echo -e "    -e \"skip_phase_3=true\"" >&2
        echo -e "" >&2
        echo -e "${BLUE}📚 See: tests/concurrent-load/concurrent-load.md | README.md${NC}" >&2
        echo -e "" >&2
        echo -e "${YELLOW}To bypass (development only): export ALLOW_UNSUPPORTED_TESTS=true${NC}" >&2
        echo -e "" >&2
        exit 1
    fi
}

# ============================================================================
# vLLM Server Connectivity Functions
# ============================================================================

check_vllm_connectivity() {
    local vllm_host="$1"
    local vllm_port="$2"
    local max_retries="${3:-30}"
    local retry_delay="${4:-5}"

    log_info "Checking vLLM server connectivity at http://${vllm_host}:${vllm_port}"

    local retry=0
    while [ $retry -lt $max_retries ]; do
        if curl -sf "http://${vllm_host}:${vllm_port}/health" >/dev/null 2>&1; then
            log_info "vLLM server is healthy"
            return 0
        fi

        retry=$((retry + 1))
        if [ $retry -lt $max_retries ]; then
            log_warn "vLLM server not ready, retrying in ${retry_delay}s (attempt $retry/$max_retries)"
            sleep "$retry_delay"
        fi
    done

    log_error "vLLM server not available after $max_retries attempts"
    return 1
}

check_vllm_models() {
    local vllm_host="$1"
    local vllm_port="$2"
    local expected_model="$3"

    log_info "Verifying model availability: ${expected_model}"

    local models_response
    if ! models_response=$(curl -sf "http://${vllm_host}:${vllm_port}/v1/models" 2>&1); then
        log_error "Failed to get models list from vLLM server"
        return 1
    fi

    if ! echo "$models_response" | grep -q "$expected_model"; then
        log_error "Expected model '${expected_model}' not found in vLLM server"
        log_debug "Available models: ${models_response}"
        return 1
    fi

    log_info "Model '${expected_model}' is available"
    return 0
}

# ============================================================================
# Configuration Loading Functions
# ============================================================================

load_config_from_yaml() {
    local yaml_file="$1"
    local key_path="$2"

    if ! command -v yq >/dev/null 2>&1; then
        log_warn "yq not installed, cannot load config from YAML"
        return 1
    fi

    if [[ ! -f "$yaml_file" ]]; then
        log_warn "YAML file not found: ${yaml_file}"
        return 1
    fi

    yq eval "$key_path" "$yaml_file" 2>/dev/null
}

# ============================================================================
# Results Directory Management
# ============================================================================

ensure_results_dir() {
    local results_dir="$1"

    if [[ -z "$results_dir" ]]; then
        log_error "Results directory not specified"
        return 1
    fi

    if [[ ! -d "$results_dir" ]]; then
        log_info "Creating results directory: ${results_dir}"
        if ! mkdir -p "$results_dir" 2>/dev/null; then
            log_error "Failed to create results directory: ${results_dir}"
            return 1
        fi
    fi

    if [[ ! -w "$results_dir" ]]; then
        log_error "Results directory is not writable: ${results_dir}"
        return 1
    fi

    log_debug "Results directory verified: ${results_dir}"
    return 0
}

# ============================================================================
# Test Execution Helpers
# ============================================================================

run_with_timeout() {
    local timeout_seconds="$1"
    shift
    local command=("$@")

    log_debug "Running command with ${timeout_seconds}s timeout: ${command[*]}"

    if command -v timeout >/dev/null 2>&1; then
        timeout "${timeout_seconds}s" "${command[@]}"
        return $?
    else
        log_warn "timeout command not available, running without timeout"
        "${command[@]}"
        return $?
    fi
}

# ============================================================================
# Metrics Extraction Helpers
# ============================================================================

extract_json_field() {
    local json_string="$1"
    local field_path="$2"

    if command -v jq >/dev/null 2>&1; then
        echo "$json_string" | jq -r "$field_path" 2>/dev/null || echo ""
    else
        log_warn "jq not installed, cannot extract JSON field: ${field_path}"
        echo ""
    fi
}

# ============================================================================
# Environment Validation
# ============================================================================

validate_environment() {
    local required_commands=("curl")
    local optional_commands=("jq" "yq" "timeout")
    local missing_required=()
    local missing_optional=()

    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_required+=("$cmd")
        fi
    done

    for cmd in "${optional_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_optional+=("$cmd")
        fi
    done

    if [[ ${#missing_required[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_required[*]}"
        log_error "Install with: sudo dnf install ${missing_required[*]}"
        return 1
    fi

    if [[ ${#missing_optional[@]} -gt 0 ]]; then
        log_warn "Missing optional commands: ${missing_optional[*]}"
        log_warn "Some features may not be available"
    fi

    log_debug "Environment validation passed"
    return 0
}
