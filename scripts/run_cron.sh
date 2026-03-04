#!/bin/bash
# Cron wrapper script for AI Research Curator
# Handles environment setup and logging

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/cron_$(date +%Y%m%d).log"

echo "=== AI Research Curator - $(date) ===" >> "${LOG_FILE}"

# Load .env if exists (includes CLAUDE_BIN_DIR, API keys, etc.)
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# Add Claude CLI path to PATH (saved by setup.sh during installation)
if [ -n "${CLAUDE_BIN_DIR}" ] && [ -d "${CLAUDE_BIN_DIR}" ]; then
    export PATH="${CLAUDE_BIN_DIR}:${PATH}"
    echo "[PATH] Claude CLI: ${CLAUDE_BIN_DIR}/claude" >> "${LOG_FILE}"
else
    echo "[PATH] CLAUDE_BIN_DIR not set, Claude CLI may not be available" >> "${LOG_FILE}"
fi

# Pull latest code from GitHub (stash local data changes first)
cd "${SCRIPT_DIR}"
echo "[Update] git pull..." >> "${LOG_FILE}"
STASHED=false
if ! git diff --quiet data/ 2>/dev/null; then
    git stash push -m "cron-auto-stash" -- data/ >> "${LOG_FILE}" 2>&1 && STASHED=true
    echo "[Update] Stashed local data changes" >> "${LOG_FILE}"
fi
git pull --ff-only >> "${LOG_FILE}" 2>&1 || echo "[Update] git pull failed, using current version" >> "${LOG_FILE}"
if [ "${STASHED}" = true ]; then
    git stash pop >> "${LOG_FILE}" 2>&1 || {
        echo "[Update] Stash pop conflict, keeping remote version for data/" >> "${LOG_FILE}"
        git checkout --theirs data/ >> "${LOG_FILE}" 2>&1
        git stash drop >> "${LOG_FILE}" 2>&1
    }
fi

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
