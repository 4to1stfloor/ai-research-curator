"""Paper summarization using LLM."""

from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


SUMMARIZE_SYSTEM_PROMPT = """당신은 생물정보학 및 AI 분야의 전문가입니다.
논문을 명확하고 이해하기 쉽게 한국어로 요약해주세요.
전문 용어는 영어 원문을 괄호 안에 병기해주세요."""

SUMMARIZE_PROMPT_TEMPLATE = """다음 논문을 한국어로 요약해주세요.

## 논문 정보
- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

## 본문 (일부)
{body_text}

---

다음 형식으로 요약해주세요:

### 핵심 발견 (Key Findings)
- (주요 발견 1-3개를 bullet point로)

### 연구 방법 (Methods)
- (사용된 주요 방법론/기술을 간략히)

### 의의 및 한계 (Significance & Limitations)
- (이 연구의 의의와 한계점)

### 한 줄 요약
(논문 전체를 한 문장으로)
"""


class PaperSummarizer:
    """Summarize papers using LLM."""

    def __init__(self, llm_client: LLMClient):
        """
        Initialize summarizer.

        Args:
            llm_client: LLM client for generation
        """
        self.llm = llm_client

    def summarize(
        self,
        paper: Paper,
        body_text: Optional[str] = None,
        max_body_chars: int = 10000
    ) -> str:
        """
        Summarize a paper.

        Args:
            paper: Paper to summarize
            body_text: Optional full text (if PDF was parsed)
            max_body_chars: Maximum characters of body text to include

        Returns:
            Summary in Korean
        """
        # Prepare body text
        body = ""
        if body_text:
            body = body_text[:max_body_chars]
            if len(body_text) > max_body_chars:
                body += "\n... (truncated)"

        # Format prompt
        prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
            title=paper.title,
            journal=paper.journal,
            authors=", ".join(paper.authors[:5]) + ("..." if len(paper.authors) > 5 else ""),
            abstract=paper.abstract or "(초록 없음)",
            body_text=body or "(본문 없음 - 초록만으로 요약)"
        )

        # Generate summary
        summary = self.llm.generate(prompt, system=SUMMARIZE_SYSTEM_PROMPT)

        return summary

    def summarize_batch(
        self,
        papers: list[Paper],
        body_texts: Optional[dict[str, str]] = None
    ) -> dict[str, str]:
        """
        Summarize multiple papers.

        Args:
            papers: List of papers to summarize
            body_texts: Optional dict of {doi/title: body_text}

        Returns:
            Dict of {paper_id: summary}
        """
        summaries = {}
        body_texts = body_texts or {}

        for paper in papers:
            paper_id = paper.doi or paper.title
            body = body_texts.get(paper_id, "")

            try:
                summary = self.summarize(paper, body)
                summaries[paper_id] = summary
                print(f"Summarized: {paper.title[:50]}...")
            except Exception as e:
                print(f"Error summarizing {paper.title[:50]}: {e}")
                summaries[paper_id] = f"(요약 생성 실패: {str(e)})"

        return summaries


# Additional prompt for generating abstract summary image description
IMAGE_DESCRIPTION_PROMPT = """다음 논문의 핵심 내용을 시각화하기 위한 다이어그램/플로우차트 설명을 작성해주세요.

## 논문 제목
{title}

## 요약
{summary}

---

Mermaid 다이어그램 코드로 이 논문의 핵심 흐름을 표현해주세요.
다이어그램은 다음을 포함해야 합니다:
1. 주요 연구 단계 또는 방법론 흐름
2. 핵심 발견 또는 결과

```mermaid 코드만 출력해주세요.
"""


class ImageDescriptionGenerator:
    """Generate diagram descriptions for papers."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_mermaid(self, paper: Paper, summary: str) -> str:
        """Generate Mermaid diagram code for paper."""
        prompt = IMAGE_DESCRIPTION_PROMPT.format(
            title=paper.title,
            summary=summary
        )

        response = self.llm.generate(prompt)

        # Extract mermaid code
        if "```mermaid" in response:
            start = response.find("```mermaid") + len("```mermaid")
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()

        return response
