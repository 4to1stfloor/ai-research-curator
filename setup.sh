#!/bin/bash
# ============================================================================
# AI Research Curator - Setup Script
# ============================================================================
# 사용법: 저장소 클론 후 실행
#   git clone https://github.com/4to1stfloor/ai-research-curator.git
#   cd ai-research-curator
#   bash setup.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  ${BOLD}AI Research Curator - Setup${NC}${CYAN}                      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# Step 1: Python check
# ============================================================================
echo -e "${CYAN}━━━ 환경 확인 ━━━${NC}"

if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo -e "  ${GREEN}✓${NC} Python: ${PY_VER}"
else
    echo -e "  ${RED}✗${NC} Python3이 설치되지 않았습니다."
    echo "    설치: https://www.python.org/downloads/"
    exit 1
fi

# ============================================================================
# Step 2: Install dependencies
# ============================================================================
echo ""
echo -e "${CYAN}━━━ 패키지 설치 ━━━${NC}"

if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
    pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>/dev/null
    echo -e "  ${GREEN}✓${NC} Python 패키지 설치 완료"
else
    echo -e "  ${YELLOW}!${NC} requirements.txt를 찾을 수 없습니다."
fi

# ============================================================================
# Step 3: AI Backend detection
# ============================================================================
echo ""
echo -e "${CYAN}━━━ AI 백엔드 감지 ━━━${NC}"

AI_FOUND=false

# Check Claude CLI
if command -v claude &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Claude CLI 감지 → API 키 없이 Claude 사용 가능"
    AI_FOUND=true
fi

# Check API keys
if [ -n "${ANTHROPIC_API_KEY}" ]; then
    echo -e "  ${GREEN}✓${NC} ANTHROPIC_API_KEY 환경변수 감지"
    AI_FOUND=true
fi

if [ -n "${GOOGLE_API_KEY}" ]; then
    echo -e "  ${GREEN}✓${NC} GOOGLE_API_KEY 환경변수 감지"
    AI_FOUND=true
fi

if [ -n "${OPENAI_API_KEY}" ]; then
    echo -e "  ${GREEN}✓${NC} OPENAI_API_KEY 환경변수 감지"
    AI_FOUND=true
fi

# Check Ollama
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json;d=json.load(sys.stdin);print(', '.join(m['name'] for m in d.get('models',[])[:3]))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} Ollama 감지 (models: ${MODELS})"
    AI_FOUND=true
elif command -v ollama &>/dev/null; then
    echo -e "  ${YELLOW}!${NC} Ollama 설치됨 (서버 미실행 → 'ollama serve'로 시작)"
fi

if [ "${AI_FOUND}" = false ]; then
    echo -e "  ${YELLOW}!${NC} AI 백엔드를 찾을 수 없습니다."
    echo "    다음 중 하나를 설정하세요:"
    echo "    1) Claude Code 설치: https://docs.anthropic.com/en/docs/claude-code"
    echo "    2) Ollama 설치: curl -fsSL https://ollama.com/install.sh | sh"
    echo "    3) API 키 설정: export ANTHROPIC_API_KEY=sk-..."
fi

# ============================================================================
# Step 4: PUBMED_EMAIL
# ============================================================================
echo ""
echo -e "${CYAN}━━━ PubMed 이메일 설정 ━━━${NC}"

ENV_FILE="${SCRIPT_DIR}/.env"

if [ -f "${ENV_FILE}" ] && grep -q "PUBMED_EMAIL" "${ENV_FILE}"; then
    CURRENT_EMAIL=$(grep "PUBMED_EMAIL" "${ENV_FILE}" | cut -d'=' -f2)
    echo -e "  ${GREEN}✓${NC} 이미 설정됨: ${CURRENT_EMAIL}"
else
    read -p "  PubMed API용 이메일 주소: " EMAIL
    if [ -n "${EMAIL}" ]; then
        echo "PUBMED_EMAIL=${EMAIL}" >> "${ENV_FILE}"
        echo -e "  ${GREEN}✓${NC} .env에 저장됨"
    else
        echo -e "  ${YELLOW}!${NC} 이메일 미입력 (나중에 .env 파일에 추가하세요)"
    fi
fi

# ============================================================================
# Step 5: Execution mode
# ============================================================================
echo ""
echo -e "${CYAN}━━━ 실행 방식 선택 ━━━${NC}"
echo ""
echo "  어떻게 실행하시겠습니까?"
echo ""
echo -e "    ${BOLD}1)${NC} 로컬 자동 실행 (crontab)"
echo "       → 이 PC에서 매주 자동 실행"
echo "       → Claude CLI / Ollama 사용 (빠름)"
echo ""
echo -e "    ${BOLD}2)${NC} GitHub Actions"
echo "       → 클라우드에서 매주 자동 실행"
echo "       → PC를 켜두지 않아도 됨"
echo "       → Ollama 사용 (느림, CPU만)"
echo ""
echo -e "    ${BOLD}3)${NC} 수동 실행만"
echo "       → 필요할 때 직접 실행"
echo ""
read -p "  선택 (1-3) [1]: " MODE

case "${MODE}" in
    2)
        echo ""
        echo -e "  ${CYAN}GitHub Actions 설정 방법:${NC}"
        echo "    1. GitHub 저장소 Settings → Secrets → Actions"
        echo "    2. New repository secret:"
        echo "       Name: PUBMED_EMAIL"
        echo "       Value: 본인 이메일"
        echo "    3. Actions 탭에서 수동 실행 또는 매주 수요일 자동 실행"
        echo ""
        echo -e "  자세한 가이드: ${BOLD}docs/GITHUB_ACTIONS_GUIDE.md${NC}"
        ;;
    3)
        echo ""
        echo -e "  ${GREEN}수동 실행 명령어:${NC}"
        echo "    python3 -m src.main --config config/config.yaml"
        echo ""
        echo "  옵션:"
        echo "    --max-papers 5    처리할 논문 수"
        echo "    --days 7          검색 기간"
        echo "    --no-pdf          PDF 리포트 생략"
        ;;
    *)
        echo ""
        bash "${SCRIPT_DIR}/scripts/setup_cron.sh" install
        ;;
esac

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  ${BOLD}Setup 완료!${NC}${CYAN}                                     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}수동 실행:${NC}"
echo "    python3 -m src.main --config config/config.yaml"
echo ""
echo -e "  ${BOLD}결과물:${NC}"
echo "    output/reports/     HTML/PDF 리포트"
echo "    output/obsidian/    Obsidian 마크다운 노트"
echo ""
echo -e "  ${BOLD}설정 변경:${NC}"
echo "    config/config.yaml  키워드, 저널, LLM 설정"
echo ""
echo -e "  ${BOLD}Cron 관리:${NC}"
echo "    bash scripts/setup_cron.sh status    상태 확인"
echo "    bash scripts/setup_cron.sh remove    제거"
echo ""
