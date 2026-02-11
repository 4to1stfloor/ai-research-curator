#!/bin/bash
# Cron wrapper script for AI Research Curator
# Handles environment setup and logging

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/cron_$(date +%Y%m%d).log"

echo "=== AI Research Curator - $(date) ===" >> "${LOG_FILE}"

# Load .env if exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# Run the pipeline
cd "${SCRIPT_DIR}"
python3 -m src.main --config config/config.yaml >> "${LOG_FILE}" 2>&1

echo "=== Completed: $(date) ===" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"
