"""Paper summarization using LLM."""

from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


SUMMARIZE_SYSTEM_PROMPT = """당신은 생물정보학(bioinformatics), 암 연구(cancer research), 인공지능(AI/ML) 분야의 전문가입니다.
논문을 깊이 있고 상세하게 한국어로 요약해주세요.
전문 용어는 영어 원문을 괄호 안에 병기하고, 필요시 간단한 설명을 덧붙여주세요.
과학적 정확성을 유지하면서도 해당 분야 대학원생이 이해할 수 있는 수준으로 작성해주세요."""

SUMMARIZE_PROMPT_TEMPLATE = """다음 논문을 한국어로 상세히 요약해주세요.

## 논문 정보
- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

## 본문 (일부)
{body_text}

---

다음 형식으로 **상세하게** 요약해주세요. 각 섹션은 충분히 자세하게 작성하세요:

### 핵심 발견 (Key Findings)
- 이 연구의 가장 중요한 발견 3-5개를 상세히 설명해주세요
- 각 발견이 왜 중요한지, 기존 연구와 어떻게 다른지 포함
- 정량적 결과가 있다면 구체적인 수치 포함

### 연구 방법 (Methods)
- 사용된 주요 기술/방법론을 단계별로 설명
- 데이터셋 정보 (샘플 수, 종류 등)
- 분석 파이프라인이나 실험 설계 설명
- 사용된 주요 도구/소프트웨어가 있다면 언급

### 연구 배경 및 동기 (Background)
- 이 연구가 해결하고자 하는 문제는 무엇인가?
- 기존 연구의 한계점은 무엇이었나?

### 의의 및 한계 (Significance & Limitations)
- 이 연구가 해당 분야에 기여하는 점
- 임상적/실용적 적용 가능성
- 연구의 한계점이나 향후 연구 방향

### 한 줄 요약
이 논문의 핵심을 한 문장으로 명확하게 요약해주세요.
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
IMAGE_DESCRIPTION_PROMPT = """다음 생물정보학/AI 논문의 연구 흐름을 Mermaid flowchart로 시각화해주세요.

## 논문 제목
{title}

## 요약
{summary}

---

## 다이어그램 요구사항

**포함해야 할 내용:**
1. 연구 배경/문제 정의 (왜 이 연구를 했는가?)
2. 주요 방법론 단계 (어떤 기술/데이터를 사용했는가?)
3. 핵심 발견/결과 (무엇을 발견했는가?)
4. 의의/영향 (이 연구가 왜 중요한가?)

**Mermaid 다이어그램 규칙:**
- flowchart TD (위에서 아래로) 형식 사용
- 노드 텍스트는 간결하게 (10단어 이내)
- 한글 사용 가능
- 주요 분기점이나 발견은 다른 모양 사용 (예: 다이아몬드, 육각형)
- 색상/스타일 적용으로 시각적 구분

**예시 형식:**
```mermaid
flowchart TD
    A[연구 배경] --> B[데이터 수집]
    B --> C{{방법론}}
    C --> D[분석 1]
    C --> E[분석 2]
    D --> F([핵심 발견])
    E --> F
    F --> G[의의/결론]

    style A fill:#e1f5fe
    style F fill:#c8e6c9
    style G fill:#fff9c4
```

**출력:**
```mermaid 코드 블록만 출력해주세요. 다른 설명은 필요 없습니다.
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
