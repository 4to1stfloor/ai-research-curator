"""Convert raw git commit messages into user-friendly Korean changelog entries."""

from pathlib import Path
from typing import Optional

from .llm_client import LLMClient


HUMANIZE_PROMPT = """다음은 AI Research Curator(논문 자동 스크래핑 도구) 프로젝트의 최근 git 커밋 메시지입니다.
이 커밋들을 사용자 입장에서 이해하기 쉬운 한국어 변경사항 목록으로 변환해주세요.

규칙:
- 각 항목은 "- "로 시작하는 한 줄로 작성
- 사용자에게 의미 있는 변경(새 기능, 개선, 버그 수정)만 포함
- "Update paper history" 같은 자동 데이터 업데이트는 제외
- "Co-Authored-By", "🤖 Generated with" 같은 부가 정보는 무시
- 기술적 용어는 사용자가 이해할 수 있는 표현으로 풀어서 작성
- 비슷한 변경사항은 합쳐서 한 줄로
- 최대 6개 항목 이내로 간결하게
- 항목 외 다른 설명/제목/머리말 절대 추가하지 마세요

커밋 목록:
{commits}

변경사항 (- 로 시작하는 줄들만):"""


class ChangelogHumanizer:
    """Use LLM to humanize raw commit messages into Korean changelog."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def humanize(self, commits: list[str]) -> Optional[str]:
        """Convert commit subject lines into a friendly Korean changelog.

        Args:
            commits: List of commit subject strings (one per commit).

        Returns:
            Markdown bullet list as a single string, or None if humanization fails.
        """
        if not commits:
            return None

        # Filter out automated history updates upfront
        meaningful = [c for c in commits if not c.lower().startswith("update paper history")]
        if not meaningful:
            return None

        commits_text = "\n".join(f"- {c}" for c in meaningful)
        prompt = HUMANIZE_PROMPT.format(commits=commits_text)

        try:
            response = self.llm.generate(prompt)
            response = response.strip()

            # Keep only lines that start with "- "
            lines = [ln.strip() for ln in response.split("\n") if ln.strip().startswith("- ")]
            if not lines:
                return None
            return "\n".join(lines)
        except Exception as e:
            print(f"[Changelog] Humanize failed: {e}")
            return None


def load_pending_changelog(pending_file: Path) -> list[str]:
    """Load commit subjects from pending_changelog.txt written by run_cron.sh.

    Format per line: "<short_hash>|<subject>"
    Returns list of subjects only (hash discarded).
    """
    if not pending_file.exists():
        return []
    subjects = []
    for line in pending_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            _, subject = line.split("|", 1)
            subjects.append(subject.strip())
        else:
            subjects.append(line)
    return subjects


def consume_pending_changelog(pending_file: Path) -> None:
    """Delete the pending changelog file after it has been displayed."""
    try:
        pending_file.unlink(missing_ok=True)
    except Exception:
        pass
