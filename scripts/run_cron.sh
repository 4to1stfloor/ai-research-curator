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

# Pull latest code from GitHub (stash any local changes first)
# We stash data/ (paper_history.json), config/ (user-customized settings),
# and src/ (in case anyone hand-edited code on this machine). Anything else
# we leave alone — that way git pull --ff-only can always succeed.
cd "${SCRIPT_DIR}"
echo "[Update] git pull..." >> "${LOG_FILE}"
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)
STASHED=false
if ! git diff --quiet HEAD -- data/ config/ src/ scripts/ 2>/dev/null; then
    git stash push -m "cron-auto-stash" -- data/ config/ src/ scripts/ >> "${LOG_FILE}" 2>&1 && STASHED=true
    echo "[Update] Stashed local changes (data/, config/, src/, scripts/)" >> "${LOG_FILE}"
fi
git pull --ff-only >> "${LOG_FILE}" 2>&1 || echo "[Update] git pull failed, using current version" >> "${LOG_FILE}"
if [ "${STASHED}" = true ]; then
    git stash pop >> "${LOG_FILE}" 2>&1 || {
        # On conflict: data/ → remote (we accumulate history from many sources),
        # config/ → local (user settings), src/ + scripts/ → remote (latest code)
        echo "[Update] Stash pop conflict, resolving by category" >> "${LOG_FILE}"
        git checkout --theirs data/ >> "${LOG_FILE}" 2>&1
        git checkout --ours config/ >> "${LOG_FILE}" 2>&1
        git checkout --theirs src/ scripts/ >> "${LOG_FILE}" 2>&1
        git add -A data/ config/ src/ scripts/ >> "${LOG_FILE}" 2>&1
        git stash drop >> "${LOG_FILE}" 2>&1
    }
fi

# Save new commits since previous run for changelog display in HTML report
NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
mkdir -p "${SCRIPT_DIR}/data"
PENDING_FILE="${SCRIPT_DIR}/data/pending_changelog.txt"
if [ -n "${OLD_HEAD}" ] && [ "${OLD_HEAD}" != "${NEW_HEAD}" ]; then
    git log --pretty=format:"%h|%s" "${OLD_HEAD}..${NEW_HEAD}" > "${PENDING_FILE}" 2>/dev/null
    NEW_COMMITS=$(wc -l < "${PENDING_FILE}")
    echo "[Update] ${NEW_COMMITS} new commits saved to changelog" >> "${LOG_FILE}"
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
