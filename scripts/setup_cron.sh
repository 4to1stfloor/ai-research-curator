#!/bin/bash
# ============================================================================
# AI Research Curator - Cron Setup Script
# ============================================================================
# Usage:
#   bash scripts/setup_cron.sh          # Install cron job
#   bash scripts/setup_cron.sh remove   # Remove cron job
#   bash scripts/setup_cron.sh status   # Check status
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_COMMENT="# ai-research-curator"
LOG_DIR="${SCRIPT_DIR}/logs"

# Default: Wednesday 09:00 KST (00:00 UTC)
CRON_SCHEDULE="0 9 * * 3"
CRON_CMD="/bin/bash ${SCRIPT_DIR}/scripts/run_cron.sh ${CRON_COMMENT}"

setup_cron() {
    echo ""
    echo "=== AI Research Curator - Cron Setup ==="
    echo ""
    echo "  Script dir : ${SCRIPT_DIR}"
    echo "  Schedule   : ${CRON_SCHEDULE} (매주 수요일 오전 9시)"
    echo "  Log dir    : ${LOG_DIR}"
    echo ""

    mkdir -p "${LOG_DIR}"

    # Remove existing job if any
    if crontab -l 2>/dev/null | grep -q "ai-research-curator"; then
        echo "  [INFO] 기존 cron job 업데이트..."
        crontab -l 2>/dev/null | grep -v "ai-research-curator" | crontab -
    fi

    # Ask for schedule preference
    echo "  실행 주기를 선택하세요:"
    echo "    1) 매주 수요일 오전 9시 (기본)"
    echo "    2) 매일 오전 9시"
    echo "    3) 매주 월요일 오전 9시"
    echo "    4) 직접 입력"
    echo ""
    read -p "  선택 (1-4) [1]: " CHOICE

    case "${CHOICE}" in
        2) CRON_SCHEDULE="0 9 * * *" ;;
        3) CRON_SCHEDULE="0 9 * * 1" ;;
        4)
            read -p "  Cron 표현식 입력 (예: 0 9 * * 3): " CRON_SCHEDULE
            ;;
        *) CRON_SCHEDULE="0 9 * * 3" ;;
    esac

    CRON_CMD="/bin/bash ${SCRIPT_DIR}/scripts/run_cron.sh ${CRON_COMMENT}"
    (crontab -l 2>/dev/null; echo "${CRON_SCHEDULE} ${CRON_CMD}") | crontab -

    echo ""
    echo "  [OK] Cron job 설치 완료!"
    echo ""
    echo "  현재 crontab:"
    crontab -l 2>/dev/null | grep "ai-research-curator"
    echo ""
    echo "  로그 확인:"
    echo "    tail -f ${LOG_DIR}/cron_\$(date +%Y%m%d).log"
    echo ""
}

remove_cron() {
    echo ""
    if crontab -l 2>/dev/null | grep -q "ai-research-curator"; then
        crontab -l 2>/dev/null | grep -v "ai-research-curator" | crontab -
        echo "  [OK] Cron job 제거 완료."
    else
        echo "  [INFO] 설치된 cron job이 없습니다."
    fi
    echo ""
}

status_cron() {
    echo ""
    echo "=== Cron Status ==="
    if crontab -l 2>/dev/null | grep -q "ai-research-curator"; then
        echo "  [ACTIVE] Cron job 활성화:"
        echo -n "  "
        crontab -l 2>/dev/null | grep "ai-research-curator"
    else
        echo "  [INACTIVE] Cron job 없음."
    fi

    echo ""
    echo "=== 최근 로그 ==="
    if [ -d "${LOG_DIR}" ]; then
        ls -lt "${LOG_DIR}/" 2>/dev/null | head -5
    else
        echo "  로그 없음."
    fi
    echo ""
}

case "${1:-install}" in
    install|setup) setup_cron ;;
    remove|uninstall) remove_cron ;;
    status) status_cron ;;
    *) echo "Usage: $0 {install|remove|status}" ; exit 1 ;;
esac
