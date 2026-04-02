#!/bin/bash
# Cleanup script to remove orphaned collect_vllm_metrics_*.py files from /tmp
# These files are created by the vllm_metrics_collector role and may persist if tests are interrupted

TEMP_DIR="${1:-/tmp}"

if [ ! -d "$TEMP_DIR" ]; then
    echo "Error: Directory not found: $TEMP_DIR"
    echo "Usage: $0 [temp_directory]"
    exit 1
fi

echo "Cleaning up collect_vllm_metrics_*.py files from temporary directory..."
echo "Searching in: $TEMP_DIR"
echo

# Find and count scripts
SCRIPT_COUNT=$(find "$TEMP_DIR" -maxdepth 1 -name "collect_vllm_metrics_*.py" -type f | wc -l)

if [ "$SCRIPT_COUNT" -eq 0 ]; then
    echo "✓ No orphaned scripts found. Temporary directory is clean!"
    exit 0
fi

echo "Found $SCRIPT_COUNT orphaned script(s):"
find "$TEMP_DIR" -maxdepth 1 -name "collect_vllm_metrics_*.py" -type f

echo
read -p "Delete these files? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    find "$TEMP_DIR" -maxdepth 1 -name "collect_vllm_metrics_*.py" -type f -delete
    echo "✓ Deleted $SCRIPT_COUNT file(s)"

    # Calculate space saved (rough estimate: ~5KB per script)
    SPACE_SAVED=$((SCRIPT_COUNT * 5))
    echo "✓ Freed ~${SPACE_SAVED}KB of disk space"
else
    echo "Cleanup cancelled."
fi
