"""Paper summarization using LLM."""

import re
from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


def remove_non_korean_foreign_chars(text: str) -> str:
    """Remove Chinese characters and other non-Korean foreign characters from text.

    Keeps:
    - Korean (Hangul): \\uAC00-\\uD7AF, \\u1100-\\u11FF
    - English letters: a-zA-Z
    - Numbers: 0-9
    - Common punctuation and symbols

    Removes:
    - Chinese characters (CJK Unified Ideographs): \\u4E00-\\u9FFF
    - Japanese Hiragana/Katakana
    - Cyrillic
    - Other foreign scripts
    """
    # Pattern for Chinese characters (CJK Unified Ideographs)
    chinese_pattern = r'[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]'

    # Pattern for Japanese (Hiragana, Katakana)
    japanese_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'

    # Pattern for Cyrillic
    cyrillic_pattern = r'[\u0400-\u04FF]'

    # Combined pattern
    foreign_pattern = f'({chinese_pattern}|{japanese_pattern}|{cyrillic_pattern})'

    # Remove foreign characters
    cleaned = re.sub(foreign_pattern, '', text)

    # Clean up any resulting double spaces
    cleaned = re.sub(r' +', ' ', cleaned)

    return cleaned


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

# Full prompt when body text is available
SUMMARIZE_PROMPT_FULL = """다음 논문을 한국어로 상세히 요약해주세요.

## 논문 정보
- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

## 본문 (일부)
{body_text}

---

**절대 준수: 전문 용어는 영어 원문 그대로 (single-cell RNA-seq, UMAP 등). 한자 절대 금지.**

다음 형식으로 요약해주세요:

### 핵심 발견 (Key Findings)
- 이 연구의 가장 중요한 발견 3-5개를 상세히 설명
- 정량적 결과가 있다면 구체적인 수치 포함

### 연구 방법 (Methods)
- 사용된 주요 기술/방법론 (기술명은 영어로)
- 데이터셋 정보 (샘플 수, 종류 등)

### 연구 배경 및 동기 (Background)
- 이 연구가 해결하고자 하는 문제

### 의의 및 한계 (Significance & Limitations)
- 이 연구의 기여점과 한계

### 한 줄 요약
이 논문의 핵심을 한 문장으로.
"""

# Simplified prompt when only abstract is available (NO PDF)
SUMMARIZE_PROMPT_ABSTRACT_ONLY = """다음 논문을 초록만 기반으로 한국어로 요약해주세요.

## 논문 정보
- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

---

**절대 준수:**
1. 전문 용어는 영어 원문 그대로 (single-cell RNA-seq, UMAP 등)
2. 한자 절대 금지 - 순수 한글과 영어만 사용
3. 초록에 없는 정보를 지어내지 마세요!

**중요: 이 논문은 PDF 본문을 확인할 수 없습니다. 초록에 명시된 내용만 기반으로 요약하세요.**

다음 형식으로 요약해주세요:

### 핵심 발견 (Key Findings)
- 초록에서 언급된 주요 발견만 작성
- 초록에 없는 내용은 추측하지 마세요

### 연구 방법 (Methods)
- 초록에 언급된 방법론만 간단히 기술
- 상세 정보 없으면: "(초록에 상세 정보 없음)"

### 한 줄 요약
이 논문의 핵심을 한 문장으로.
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
        authors_str = ", ".join(paper.authors[:5]) + ("..." if len(paper.authors) > 5 else "")

        # Choose prompt based on body text availability
        if body_text and len(body_text.strip()) > 100:
            # Full prompt with body text
            body = body_text[:max_body_chars]
            if len(body_text) > max_body_chars:
                body += "\n... (truncated)"

            prompt = SUMMARIZE_PROMPT_FULL.format(
                title=paper.title,
                journal=paper.journal,
                authors=authors_str,
                abstract=paper.abstract or "(초록 없음)",
                body_text=body
            )
        else:
            # Abstract-only prompt (no hallucination)
            prompt = SUMMARIZE_PROMPT_ABSTRACT_ONLY.format(
                title=paper.title,
                journal=paper.journal,
                authors=authors_str,
                abstract=paper.abstract or "(초록 없음)"
            )

        # Generate summary
        summary = self.llm.generate(prompt, system=SUMMARIZE_SYSTEM_PROMPT)

        # Post-process to remove any Chinese/Japanese/Cyrillic characters
        summary = remove_non_korean_foreign_chars(summary)

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

        # Post-process to remove any Chinese/Japanese/Cyrillic characters
        response = remove_non_korean_foreign_chars(response)

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
