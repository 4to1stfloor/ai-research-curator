"""Paper summarization using LLM."""

import re
from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


def remove_llm_preamble(text: str) -> str:
    """Remove LLM preamble/introduction text from summaries.

    Removes common patterns like:
    - "네, ~하겠습니다."
    - "알겠습니다. ~드리겠습니다."
    - "다음은 ~입니다."
    """
    import re

    # Patterns to remove at the start of the text
    preamble_patterns = [
        # "네, ~하겠습니다/드리겠습니다" pattern
        r'^네[,.]?\s*[^\n]*(?:하겠습니다|드리겠습니다|겠습니다)[.!]?\s*',
        # "알겠습니다" pattern
        r'^알겠습니다[.!]?\s*[^\n]*(?:하겠습니다|드리겠습니다)[.!]?\s*',
        # "다음은 ~입니다" pattern
        r'^다음은[^\n]*입니다[.!]?\s*',
        # "요약해 드리겠습니다" standalone
        r'^[^\n]*요약해[^\n]*드리겠습니다[.!]?\s*',
        # "전문가 관점에서" pattern
        r'^[^\n]*전문가\s*관점에서[^\n]*[.!]?\s*',
        # Horizontal rule after preamble
        r'^-{3,}\s*',
        # Empty lines at start
        r'^\s*\n+',
    ]

    result = text
    for pattern in preamble_patterns:
        result = re.sub(pattern, '', result, flags=re.MULTILINE)

    # Also remove "---" separator lines that appear after preamble removal
    result = re.sub(r'^\s*-{3,}\s*\n?', '', result, flags=re.MULTILINE)

    return result.strip()


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
    - Thai, Arabic, Hebrew, and other foreign scripts
    """
    # Pattern for Chinese characters (CJK Unified Ideographs)
    chinese_pattern = r'[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]'

    # Pattern for Japanese (Hiragana, Katakana)
    japanese_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'

    # Pattern for Cyrillic
    cyrillic_pattern = r'[\u0400-\u04FF]'

    # Pattern for Thai
    thai_pattern = r'[\u0E00-\u0E7F]'

    # Pattern for Arabic
    arabic_pattern = r'[\u0600-\u06FF\u0750-\u077F]'

    # Pattern for Hebrew
    hebrew_pattern = r'[\u0590-\u05FF]'

    # Pattern for other scripts (Greek, etc.)
    greek_pattern = r'[\u0370-\u03FF]'

    # Combined pattern
    foreign_pattern = f'({chinese_pattern}|{japanese_pattern}|{cyrillic_pattern}|{thai_pattern}|{arabic_pattern}|{hebrew_pattern}|{greek_pattern})'

    # Remove foreign characters
    cleaned = re.sub(foreign_pattern, '', text)

    # Clean up any resulting double spaces
    cleaned = re.sub(r' +', ' ', cleaned)

    return cleaned


SUMMARIZE_SYSTEM_PROMPT = """당신은 생명과학/의학 분야 논문 요약 전문가입니다.

**핵심 규칙:**
1. **세포명, 조직명, 해부학 용어는 반드시 영어 그대로 유지:**
   - melanocyte, fibroblast, macrophage, T cell, B cell, neuron → 영어 그대로
   - neural crest, epidermis, dermis, adipose tissue → 영어 그대로
   - 절대 음역 금지: "며느기" (X), "멜라노사이트" (X) → "melanocyte" (O)

2. 전문 용어는 영어 그대로 사용하거나 공식 한국어 용어만 사용:
   - epigenome → "epigenome" 또는 "후성유전체" (에피지놈 X)
   - transcriptome → "transcriptome" 또는 "전사체"
   - genome → "genome" 또는 "유전체" (지놈 X)
   - chromatin → "chromatin" 또는 "염색질"
   - CRISPR-Cas9, single-cell RNA-seq, spatial transcriptomics → 영어 그대로

3. 음역(발음을 한글로 옮기기) 절대 금지:
   - 금지 예시: 에피겐ôm, 트랜스크립톰, 지놈, 크로마틴, 며느기 등
   - 영어 그대로 쓰거나 공식 번역어만 사용

4. 유전자명, 단백질명, 기술명은 영어 그대로:
   - p53, BRCA1, H3K27ac, dCas9-p300, UMAP, t-SNE, BMP, ID1

5. 한글과 영어만 사용 (한자, 일본어, 기타 외국어, 특수문자 금지)"""

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

**절대 준수: 전문 용어는 영어 그대로(single-cell RNA-seq, epigenome 등) 또는 공식 한국어(후성유전체, 전사체 등). 음역 금지(에피지놈 X).**

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
1. 전문 용어는 영어 그대로 또는 공식 한국어(epigenome→후성유전체, 음역 금지)
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

        # Remove LLM preamble (e.g., "네, 전문가 관점에서...요약해 드리겠습니다")
        summary = remove_llm_preamble(summary)

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
1. **전문 용어는 반드시 영어 그대로 유지**:
   - 세포명: melanocyte, fibroblast, macrophage, T cell 등 → 영어 그대로
   - 분자명: RNA, DNA, protein, gene 등 → 영어 그대로
   - 기술명: single-cell RNA-seq, ATAC-seq, UMAP, t-SNE 등 → 영어 그대로
   - 해부학: neural crest, epidermis, dermis 등 → 영어 그대로
   - 음역 절대 금지: "며느기" (X), "멜라노사이트" (X) → "melanocyte" (O)

2. 한자(漢字)와 다른 언어 절대 금지: 순수 한글과 영어만 사용

3. **Figure는 반드시 번호 순서대로 설명** (Figure 1 → Figure 2 → Figure 3...)

4. 해당 분야 대학원생이 이해할 수 있도록 설명하세요

다음 형식으로 **번호 순서대로** Figure를 설명해주세요:

#### Figure 1: (Figure 1 제목)
**핵심 내용**: (이 Figure가 보여주는 가장 중요한 결과)
**세부 설명**:
- Panel별 주요 내용
- 분석 방법 및 그래프 해석

#### Figure 2: (Figure 2 제목)
**핵심 내용**: ...
**세부 설명**: ...

(이후 Figure도 같은 형식으로 번호 순서대로)
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
