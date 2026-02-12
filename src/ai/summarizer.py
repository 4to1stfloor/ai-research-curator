"""Paper summarization using LLM."""

import re
from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


def fix_summary_terminology(text: str) -> str:
    """Fix incorrectly translated/transliterated scientific terminology in summaries.

    LLMs often ignore instructions to keep technical terms in English.
    This function forcibly corrects common mistranslations.
    """
    # Dictionary of wrong translations → correct English terms
    replacements = {
        # Omics - wrong transliterations
        '트랜스크립톰': 'transcriptome',
        '트랜스크립토믹스': 'transcriptomics',
        '트랜스ptomics': 'transcriptomics',
        '전사체 연구': 'transcriptomics',
        '에피지놈': 'epigenome',
        '에피겐': 'epigenome',
        '에피지노믹': 'epigenomic',
        '지놈': 'genome',
        '지노믹': 'genomic',
        '프로테옴': 'proteome',
        '메타볼롬': 'metabolome',

        # Spatial terms
        '스페이셜리': 'spatially',
        '스페이셜': 'spatial',
        '레솔브드': 'resolved',
        'spatially 레솔브드': 'spatially resolved',
        '공간적으로 분리된': 'spatially resolved',
        '공간적으로 해결된': 'spatially resolved',
        '공간분해': 'spatially resolved',
        '공간 전사체': 'spatial transcriptomics',

        # Epigenetics terms
        '뉴클리오솜': 'nucleosome',
        '뉴클레오솜': 'nucleosome',
        '핵소체': 'nucleosome',
        '크로마틴': 'chromatin',
        '히스톤': 'histone',
        '메틸화': 'methylation',
        '아세틸화': 'acetylation',

        # Methods
        '싱글셀': 'single-cell',
        '단일세포': 'single-cell',

        # Network/model terms
        '스페이셜 트랜스크립톰 아뷰트 셀 네트워크': 'spatial transcriptomics Attribute Cell Network (stACN)',
        '스페이셜 트랜스크립톰 아티뷰트 셀 네트워크': 'spatial transcriptomics Attribute Cell Network (stACN)',
        '스페이셜 트랜스크립톰': 'spatial transcriptomics',
        '아뷰트': 'attribute',
        '아티뷰트': 'attribute',

        # Common mistranslations
        'facilite': '촉진',
        'facilitates': '촉진',
    }

    result = text
    for wrong, correct in replacements.items():
        result = result.replace(wrong, correct)

    return result


def remove_llm_preamble(text: str) -> str:
    """Remove LLM preamble/introduction text from summaries.

    Removes common patterns like:
    - "# 논문 요약: ..." / "## 논문 요약: ..."
    - "# Paper Title 요약"
    - Paper title as first heading (not a section heading)
    - "네, ~하겠습니다."
    - "알겠습니다. ~드리겠습니다."
    - "다음은 ~입니다."
    """
    import re

    # Patterns to remove at the start of the text
    preamble_patterns = [
        # "# 논문 요약: ..." or "## 논문 요약: ..." title line added by LLM
        r'^#{1,4}\s*논문\s*요약[:\s][^\n]*\n?',
        # "# Title 요약" - paper title heading ending with "요약"
        r'^#{1,4}\s+[^\n]+요약\s*\n?',
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

    # Remove first heading if it's not an expected section name
    # (catches LLM outputting paper title as first heading)
    result = result.strip()
    expected_sections = [
        '핵심 발견', 'Key Findings', '연구 방법', 'Methods',
        '연구 배경', 'Background', '의의', 'Significance',
        '한 줄 요약', 'One-line Summary',
    ]
    first_line_match = re.match(r'^(#{1,4})\s+([^\n]+)\n?', result)
    if first_line_match:
        heading_text = first_line_match.group(2).strip()
        if not any(section in heading_text for section in expected_sections):
            result = result[first_line_match.end():]

    # Also remove "---" separator lines that appear after preamble removal
    result = re.sub(r'^\s*-{3,}\s*\n?', '', result, flags=re.MULTILINE)

    return result.strip()


def remove_meta_commentary(text: str) -> str:
    """Remove AI meta-commentary about input text quality/completeness.

    Removes patterns like:
    - "제공된 초록과 본문이 불완전하여..."
    - "본문에서 잘림"
    - "전체 내용을 파악하기 어렵습니다"
    """
    import re

    # Patterns for meta-commentary lines/sentences to remove
    meta_patterns = [
        # "제공된 ~가 불완전하여" full sentence
        r'[^\n]*제공된[^\n]*불완전하여[^\n]*\n?',
        # "문장이 중간에 끊김" meta note
        r'[^\n]*문장이\s*중간에\s*끊[^\n]*\n?',
        # "전체 내용을 파악하기 어렵" meta note
        r'[^\n]*전체\s*내용을\s*파악하기\s*어렵[^\n]*\n?',
        # "제공된 정보만을 바탕으로" meta note
        r'[^\n]*제공된\s*정보만[^\n]*바탕으로[^\n]*\n?',
        # "제공된 정보가 불완전" meta note
        r'[^\n]*제공된\s*정보가\s*불완전[^\n]*\n?',
        # "(구체적 ~은/는 본문에서 잘림)" parenthetical meta
        r'\s*\([^)]*본문에서\s*잘림[^)]*\)',
        # "(정보 부족)" parenthetical meta
        r'\s*\([^)]*정보\s*부족[^)]*\)',
        # "(본문에서 확인 불가)" parenthetical meta
        r'\s*\([^)]*확인\s*불가[^)]*\)',
        # "~ 파악 불가" at end of bullet
        r'\s*파악\s*불가\s*$',
    ]

    result = text
    for pattern in meta_patterns:
        result = re.sub(pattern, '', result, flags=re.MULTILINE)

    # Clean up empty list items
    result = re.sub(r'^-\s*\*\*한계\*\*:\s*\n', '', result, flags=re.MULTILINE)

    # Clean up multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)

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


SUMMARIZE_SYSTEM_PROMPT = """당신은 생명과학/의학 분야 논문 요약 전문가입니다. 전문 용어는 반드시 영어로 유지하세요."""

# Full prompt when body text is available
SUMMARIZE_PROMPT_FULL = """다음 논문을 한국어로 요약해주세요.

## 예시 요약 (이 스타일을 정확히 따라주세요):

**예시 논문**: "Spatially resolved transcriptomics reveals cell type heterogeneity"

### 핵심 발견 (Key Findings)
1. **Spatially resolved transcriptomics를 이용한 cell type mapping**: Tissue section에서 다양한 cell type의 spatial distribution을 확인하였다.
2. **stACN model 개발**: Graph noise model과 joint tensor decomposition을 활용한 새로운 network model을 개발하였다.
3. **성능 향상**: Adjusted Rand Index (ARI) 기준으로 기존 방법 대비 clustering 성능이 향상되었다.

### 연구 방법 (Methods)
- Spatially resolved transcriptomics (SRT) 데이터 분석
- Graph noise model 기반 denoising
- Joint tensor decomposition
- 평가 지표: Adjusted Rand Index (ARI)

### 연구 배경 및 동기 (Background)
- SRT 데이터는 gene expression과 spatial information을 동시에 제공하지만 technical noise가 많다.
- 기존 방법은 denoising과 spatial domain identification을 별도로 수행하여 성능이 저하된다.

### 의의 및 한계 (Significance & Limitations)
- 의의: Denoising과 spatial domain identification을 통합한 최초의 방법론
- 한계: 특정 SRT platform에서만 검증됨

### 한 줄 요약
Spatially resolved transcriptomics data의 denoising과 spatial domain identification을 동시에 수행하는 stACN model을 제안하였다.

---

## 요약할 논문:

- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

## 본문 (일부)
{body_text}

---

**절대 규칙 (MUST FOLLOW):**
1. 모든 전문 용어는 영어 그대로 쓰세요:
   - "spatially resolved transcriptomics" (O) / "스페이셜리 리졸브드" (X)
   - "spatial transcriptomics" (O) / "공간 전사체" (X)
   - "denoising" (O) / "노이즈 제거" (X)
   - "single-cell RNA-seq" (O) / "단일세포" (X)
2. 초록과 본문에 있는 내용만 쓰세요. 없는 내용을 지어내지 마세요.
3. 제공된 텍스트의 품질, 완전성, 잘림 여부에 대해 절대 언급하지 마세요:
   - "제공된 초록과 본문이 불완전하여" (X)
   - "문장이 중간에 끊김" (X)
   - "본문에서 잘림" (X)
   - "전체 내용을 파악하기 어렵습니다" (X)
   - "제공된 정보만을 바탕으로" (X)
   - "제공된 정보가 불완전하여" (X)
   금지! 있는 내용만으로 자연스럽게 요약하세요.

위 예시처럼 전문 용어를 영어로 유지하면서 요약해주세요.
"""

# Simplified prompt when only abstract is available (NO PDF)
SUMMARIZE_PROMPT_ABSTRACT_ONLY = """다음 논문을 초록만 기반으로 한국어로 요약해주세요.

## 예시 요약 (이 스타일을 정확히 따라주세요):

**예시 논문**: "Spatially resolved transcriptomics reveals cell type distributions"

### 핵심 발견 (Key Findings)
1. **Spatially resolved transcriptomics를 이용한 cell type mapping**: Tissue section에서 다양한 cell type의 spatial distribution을 확인하였다.
2. **Denoising 방법론 개발**: stACN이라는 새로운 network model을 통해 data quality를 향상시켰다 (ARI score 개선).
3. **Spatial domain identification**: Graph noise model과 joint tensor decomposition을 활용하여 spatial domain을 식별하였다.

### 연구 방법 (Methods)
- Spatially resolved transcriptomics (SRT) 데이터 분석
- Graph noise model 기반 denoising
- Joint tensor decomposition
- Adjusted Rand Index (ARI)로 성능 평가

### 한 줄 요약
Spatially resolved transcriptomics data의 denoising과 spatial domain identification을 동시에 수행하는 stACN model을 제안하였다.

---

## 요약할 논문:

- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

---

**절대 규칙 (MUST FOLLOW):**
1. 모든 전문 용어는 영어 그대로 쓰세요:
   - "spatially resolved transcriptomics" (O) / "스페이셜리 리졸브드" (X)
   - "spatial transcriptomics" (O) / "공간 전사체" (X)
   - "denoising" (O) / "노이즈 제거" (X)
   - "single-cell RNA-seq" (O) / "단일세포" (X)
2. 초록에 있는 내용만 쓰세요. 없는 내용을 지어내지 마세요.
3. 제공된 텍스트의 품질, 완전성, 잘림 여부에 대해 절대 언급하지 마세요:
   - "제공된 초록이 불완전하여" (X)
   - "정보가 제한적이어서" (X)
   - "제공된 정보만을 바탕으로" (X)
   금지! 있는 내용만으로 자연스럽게 요약하세요.

위 예시처럼 전문 용어를 영어로 유지하면서 요약해주세요.
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
        max_body_chars: int = 20000
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
            # Full prompt with body text (truncate silently without marker)
            body = body_text[:max_body_chars]

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

        # Post-process: fix incorrectly translated terminology first
        summary = fix_summary_terminology(summary)

        # Post-process to remove any Chinese/Japanese/Cyrillic characters
        summary = remove_non_korean_foreign_chars(summary)

        # Remove LLM preamble (e.g., "네, 전문가 관점에서...요약해 드리겠습니다")
        summary = remove_llm_preamble(summary)

        # Remove AI meta-commentary about input quality/completeness
        summary = remove_meta_commentary(summary)

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

## 예시 Figure 해설 (이 스타일을 정확히 따라주세요):

#### Figure 1: Spatially resolved transcriptomics workflow
**핵심 내용**: Spatially resolved transcriptomics 실험 workflow와 stACN model의 구조를 보여준다.
**세부 설명**:
- Panel A: stACN model의 전체 workflow. Input으로 SRT data를 받아 denoising과 spatial domain identification을 수행한다.
- Panel B: Graph noise model을 통한 dual cell network 학습 과정.
- Panel C: Joint tensor decomposition을 통한 cell feature 추출.

#### Figure 2: Spatial domain identification 결과
**핵심 내용**: stACN model의 spatial domain identification 결과를 기존 방법과 비교한다.
**세부 설명**:
- Panel A: Ground truth annotation과 stACN 결과 비교. Spatial domain이 정확하게 식별되었다.
- Panel B: Adjusted Rand Index (ARI) score 비교. stACN이 기존 방법 대비 높은 성능을 보인다.

---

## 해설할 논문:

### 논문 제목
{title}

### 논문 요약
{summary}

### Figure Legend (논문에서 추출)
{figure_legend}

---

**절대 규칙 (MUST FOLLOW):**
1. 모든 전문 용어는 영어 그대로 쓰세요:
   - "spatially resolved transcriptomics" (O) / "스페이셜리 리졸브드" (X)
   - "spatial domain identification" (O) / "공간 도메인 식별" (X)
   - "denoising" (O) / "노이즈 제거" (X)
   - "UMAP", "clustering", "cell type" (O) / 한글 음역 (X)
2. 논문 내용에 기반해서만 설명하세요. 없는 내용을 지어내지 마세요.
3. 바로 "#### Figure 1:" 형식으로 시작하세요. 서론, 인사말, 메타 설명 절대 금지:
   - "이 논문의 Figure를 설명하겠습니다" (X)
   - "Figure 파일이 아직 추출되지 않은 것 같습니다" (X)
   - "PDF에서 직접 Figure 내용을 확인했으므로" (X)
   금지! 바로 Figure 설명만 출력하세요.

위 예시처럼 전문 용어를 영어로 유지하면서 Figure를 순서대로 설명해주세요.
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

        # Post-process: remove AI preamble before first figure heading
        import re
        fig_match = re.search(r'#+\s*Figure\s*\d', response)
        if fig_match:
            response = response[fig_match.start():]
        else:
            # No markdown figure headings - check for meta-commentary
            meta_patterns = [
                r'이미지를?\s*확인해야',
                r'이미지\s*파일.*경로',
                r'공유해\s*주시',
                r'알려주시.*경로',
                r'Figure\s*이미지.*확인',
                r'정확한\s*설명.*드리기\s*어렵',
            ]
            if any(re.search(p, response) for p in meta_patterns):
                return ""
            # Otherwise keep as-is (LLM may have used different formatting)

        # Post-process: fix incorrectly translated terminology first
        response = fix_summary_terminology(response)

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
