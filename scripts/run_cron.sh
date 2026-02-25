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

# Pull latest code from GitHub
cd "${SCRIPT_DIR}"
echo "[Update] git pull..." >> "${LOG_FILE}"
git pull --ff-only >> "${LOG_FILE}" 2>&1 || echo "[Update] git pull failed, using current version" >> "${LOG_FILE}"

# Setup venv if not exists, then activate
VENV_DIR="${SCRIPT_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo "[Setup] Creating venv..." >> "${LOG_FILE}"
    python3 -m venv "${VENV_DIR}" >> "${LOG_FILE}" 2>&1
fi
source "${VENV_DIR}/bin/activate"

# Update dependencies if requirements changed
pip install -r requirements.txt -q >> "${LOG_FILE}" 2>&1

# Run the pipeline
python3 -m src.main --config config/config.yaml >> "${LOG_FILE}" 2>&1

echo "=== Completed: $(date) ===" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"
