"""Paper summarization using LLM."""

from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


SUMMARIZE_SYSTEM_PROMPT = """당신은 생물정보학(bioinformatics), 암 연구(cancer research), 인공지능(AI/ML) 분야의 전문가입니다.
논문을 깊이 있고 상세하게 한국어로 요약해주세요.

**절대 준수 규칙:**
1. 전문 용어는 영어 원문을 그대로 사용하세요:
   - 좋은 예: "single-cell RNA-seq", "spatial transcriptomics", "random forest", "contrastive learning"
   - 나쁜 예: "단일세포 RNA 시퀀싱", "공간 전사체학", "무작위 숲"

2. 한자(漢字)와 다른 언어 절대 금지:
   - 금지: 高, 展示, 混合, 能力 등 한자
   - 금지: демонстрирует 등 다른 언어
   - 반드시 순수 한글(가나다...)과 영어(ABC...)만 사용하세요
   - "고해상도" (O), "高해상도" (X)
   - "보여준다" (O), "展示한다" (X)

3. 유전자명, 단백질명, 알고리즘명은 영어 원문 그대로: p53, BRCA1, UMAP, t-SNE

4. 과학적 정확성을 유지하면서 대학원생 수준으로 작성하세요."""

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

**중요: 전문 용어는 영어 원문을 그대로 사용하세요 (예: single-cell RNA-seq, spatial transcriptomics, random forest). 한자는 절대 사용하지 마세요.**

다음 형식으로 상세하게 요약해주세요:

### 핵심 발견 (Key Findings)
- 이 연구의 가장 중요한 발견 3-5개를 상세히 설명
- 각 발견이 왜 중요한지, 기존 연구와 어떻게 다른지 포함
- 정량적 결과가 있다면 구체적인 수치 포함

### 연구 방법 (Methods)
- 사용된 주요 기술/방법론을 단계별로 설명 (기술명은 영어로)
- 데이터셋 정보 (샘플 수, 종류 등)
- 분석 파이프라인이나 실험 설계 설명
- 사용된 주요 도구/소프트웨어 언급

### 연구 배경 및 동기 (Background)
- 이 연구가 해결하고자 하는 문제는 무엇인가?
- 기존 연구의 한계점은 무엇이었나?

### 의의 및 한계 (Significance & Limitations)
- 이 연구가 해당 분야에 기여하는 점
- 임상적/실용적 적용 가능성
- 연구의 한계점이나 향후 연구 방향

### 한 줄 요약
이 논문의 핵심을 한 문장으로 명확하게 요약하세요.
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


# Prompt for generating figure explanations
FIGURE_EXPLANATION_PROMPT = """다음 논문의 Figure를 설명해주세요.

## 논문 제목
{title}

## 논문 요약
{summary}

## Figure Legend (논문에서 추출)
{figure_legend}

---

**절대 준수 규칙:**
1. 전문 용어는 영어 원문 그대로 사용: single-cell RNA-seq, UMAP, clustering, contrastive learning
2. 한자(漢字)와 다른 언어 절대 금지: 순수 한글과 영어만 사용
   - "고해상도" (O), "高해상도" (X)
   - "보여준다" (O), "展示한다" (X)
3. 해당 분야 대학원생이 이해할 수 있도록 설명하세요

다음 형식으로 Figure를 설명해주세요:

### Figure 설명

**핵심 내용**: (이 Figure가 보여주는 가장 중요한 결과를 1-2문장으로)

**세부 설명**:
- Panel별 주요 내용 설명
- 사용된 분석 방법 설명
- 그래프/플롯의 축과 의미 설명

**해석 포인트**:
- 이 Figure에서 주목해야 할 점
- 연구 결론과의 연결점
"""


class FigureExplanationGenerator:
    """Generate explanations for paper figures."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_explanation(
        self,
        paper: Paper,
        summary: str,
        figure_legend: str = ""
    ) -> str:
        """
        Generate explanation for paper figures.

        Args:
            paper: Paper object
            summary: Paper summary
            figure_legend: Figure legend text from paper

        Returns:
            Figure explanation in Korean
        """
        prompt = FIGURE_EXPLANATION_PROMPT.format(
            title=paper.title,
            summary=summary,
            figure_legend=figure_legend or "(Figure legend 없음)"
        )

        response = self.llm.generate(prompt)
        return response

    def extract_figure_legends(self, text: str) -> list[dict]:
        """
        Extract figure legends from paper text.

        Args:
            text: Full paper text

        Returns:
            List of {"figure_num": str, "legend": str}
        """
        import re
        legends = []

        # Pattern for figure legends (e.g., "Figure 1.", "Fig. 1:", "Figure 1:")
        pattern = r'(?:Figure|Fig\.?)\s*(\d+[A-Za-z]?)[\.:]\s*([^\n]+(?:\n(?![A-Z])[^\n]+)*)'
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for match in matches:
            fig_num = match.group(1)
            legend = match.group(2).strip()
            # Clean up legend text
            legend = re.sub(r'\s+', ' ', legend)
            legends.append({
                "figure_num": fig_num,
                "legend": legend[:500]  # Limit length
            })

        return legends
