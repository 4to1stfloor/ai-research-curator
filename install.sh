#!/bin/bash
# ============================================================
# AI Research Curator - One-Line Installer
# ============================================================
# 사용법:
#   curl -fsSL https://raw.githubusercontent.com/4to1stfloor/ai-research-curator/main/install.sh | bash
#
# 이 스크립트가 하는 일:
#   1. ~/.ai-research-curator/ 에 도구 설치 (또는 업데이트)
#   2. setup.sh 실행 (환경 확인, AI 감지, 실행 방식 선택)
# ============================================================

set -e

INSTALL_DIR="${HOME}/.ai-research-curator"
REPO_URL="https://github.com/4to1stfloor/ai-research-curator.git"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  ${BOLD}AI Research Curator - Installer${NC}${CYAN}                 ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Check git
if ! command -v git &>/dev/null; then
    echo -e "  ${YELLOW}✗${NC} git이 설치되지 않았습니다."
    echo "    설치 후 다시 실행하세요."
    exit 1
fi

# Step 2: Clone or update
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo -e "  ${GREEN}✓${NC} 이미 설치됨 → 업데이트 중..."
    cd "${INSTALL_DIR}" && git pull -q origin main 2>/dev/null || true
else
    echo -e "  ${CYAN}→${NC} 설치 중... (${INSTALL_DIR})"
    git clone -q "${REPO_URL}" "${INSTALL_DIR}" 2>/dev/null
fi
echo -e "  ${GREEN}✓${NC} 설치 완료: ${INSTALL_DIR}"

# Step 3: Run setup
cd "${INSTALL_DIR}"
echo ""
exec bash "${INSTALL_DIR}/setup.sh" < /dev/tty
