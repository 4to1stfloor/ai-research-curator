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

    # Remove ALL markdown headings (new prose format should have none)
    result = re.sub(r'^#{1,4}\s+[^\n]*\n?', '', result.strip(), flags=re.MULTILINE)

    # Also remove "---" separator lines that appear after preamble removal
    result = re.sub(r'^\s*-{3,}\s*\n?', '', result, flags=re.MULTILINE)

    # Remove bullet points and numbered lists (convert to plain text)
    result = re.sub(r'^[-*]\s+', '', result, flags=re.MULTILINE)
    result = re.sub(r'^\d+\.\s+', '', result, flags=re.MULTILINE)

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


def ensure_paragraph_breaks(text: str) -> str:
    """Ensure prose summary has proper paragraph breaks (4 paragraphs).

    If the LLM outputs text without blank line separators between paragraphs,
    insert breaks after the first sentence (one-line overview) and detect
    paragraph transitions.
    """
    import re

    # Already has paragraph breaks (3+ blank lines = 4+ paragraphs)
    paragraphs = re.split(r'\n\s*\n', text.strip())
    if len(paragraphs) >= 3:
        return text  # Already properly formatted

    # Try to split: first sentence ending with "연구입니다." is paragraph 1
    # Then look for natural paragraph transitions
    lines = text.strip().split('\n')
    result_paragraphs = []
    current = []

    for line in lines:
        line = line.strip()
        if not line:
            if current:
                result_paragraphs.append(' '.join(current))
                current = []
            continue

        # If current paragraph is empty and we're starting fresh
        if not current:
            current.append(line)
            # Check if this line alone is the one-line overview
            if re.search(r'연구입니다[.。]?\s*$', line):
                result_paragraphs.append(' '.join(current))
                current = []
            continue

        # Check if this line starts a new paragraph topic
        # (after the overview, detect transitions to background/findings/significance)
        if len(result_paragraphs) >= 1 and re.search(
            r'(연구입니다|습니다|었습니다|입니다)[.。]?\s*$', ' '.join(current)
        ) and len(' '.join(current)) > 100:
            result_paragraphs.append(' '.join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        result_paragraphs.append(' '.join(current))

    # If we got reasonable paragraphs (2+), join with blank lines
    if len(result_paragraphs) >= 2:
        return '\n\n'.join(result_paragraphs)

    return text


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
전문 용어(유전자명, 단백질명, 기술명, 방법론 등)는 반드시 영어로 유지하세요.
출력은 순수 한국어 산문체로 작성하되, 마크다운 헤딩(#, ##), 불릿 포인트(-, *), 번호 목록(1., 2.)은 절대 사용하지 마세요.
반드시 4개의 문단으로만 구성하세요."""

# Full prompt when body text is available
SUMMARIZE_PROMPT_FULL = """다음 논문을 한국어로 요약해주세요.

## 출력 형식 (반드시 이 4문단 구조를 따르세요):

문단1 - 한 줄 개요: 이 논문이 무엇을 한 연구인지 1문장으로 요약.
문단2 - 연구 배경: 질환/분야의 맥락, 기존에 알려진 사실, 해결되지 않은 문제, 이 연구의 동기.
문단3 - 핵심 발견: 연구진이 수행한 분석과 구체적 결과. 어떤 방법을 썼고, 무엇을 발견했는지.
문단4 - 의의: 이 연구가 해당 분야에 미치는 영향, 임상적/학문적 함의, 향후 전망.

각 문단 사이에 반드시 빈 줄을 넣으세요 (총 4개 문단, 3개 빈 줄).
마크다운 헤딩(#), 불릿(-), 번호(1.)는 절대 사용하지 마세요.

## 예시 1:

Proteogenomics 분석을 통해 진행성 differentiated thyroid cancer의 분자 아형과 치료 반응 차이를 보여준 연구입니다.

Differentiated thyroid cancer(DTC)은 일반적으로 예후가 좋은 암으로 알려져 있지만, 일부 환자에서는 locally advanced 또는 metastatic 단계로 진행하면서 치료 반응이 크게 달라지는 임상적 이질성이 나타납니다. 기존 연구에서는 BRAF, RAS, TERT promoter mutation과 같은 유전자 이상이 질병의 진행과 관련이 있다는 점이 알려져 있었지만, 실제 치료 전략과 직접적으로 연결되는 통합적 분류 체계는 부족했습니다. 이에 연구진은 진행성 DTC의 분자적 특성을 보다 정밀하게 이해하기 위해 proteogenomics 접근을 적용하여 질병의 생물학적 아형을 규명하고자 하였습니다.

연구진은 진행성 DTC 환자 샘플을 대상으로 proteomic profiling과 genomic 분석을 통합하여 세 가지 주요 분자 아형을 규명했습니다. 첫 번째는 thyroid differentiation 기능이 비교적 잘 유지된 canonical subtype(CC1), 두 번째는 tumor stroma와 angiogenesis 관련 신호가 강한 stromal subtype(CC2), 세 번째는 immune cell infiltration과 immune signaling이 두드러지는 immunogenic subtype(CC3)입니다. 이 세 아형은 mutation 패턴, tumor microenvironment, radioactive iodine(RAI) 치료 반응 및 progression-free survival(PFS)에서 서로 뚜렷한 차이를 보였습니다. 특히 CC1은 RAI 치료 반응이 가장 좋았으며, CC2는 anti-angiogenic therapy에 반응할 가능성이 높았고, CC3는 immunotherapy 전략과 연관될 가능성이 제시되었습니다.

이 연구는 진행성 DTC가 단일한 질환이 아니라 서로 다른 생물학적 특성을 가진 세 가지 분자 아형으로 구성된 질환 스펙트럼임을 보여주었습니다. 또한 이러한 분류가 단순한 분자적 차이를 넘어 실제 치료 반응과 예후 차이로 이어질 수 있음을 제시하였습니다. 향후 진행성 DTC 치료는 기존의 획일적인 접근이 아니라 subtype 기반 precision medicine 전략으로 발전할 가능성이 있으며, proteogenomics 기반 분석이 임상 의사결정에 중요한 역할을 할 수 있음을 시사합니다.

## 예시 2:

장내미생물 대사 분석을 통해 MASH fibrosis 기전을 보여준 연구입니다.

Metabolic dysfunction-associated steatotic liver disease(MASLD)은 일부 환자에서 염증과 fibrosis를 동반한 metabolic dysfunction-associated steatohepatitis(MASH)으로 진행하며, 이 단계에서 cirrhosis와 hepatocellular carcinoma 위험이 크게 증가합니다. 그동안 과도한 당, 특히 fructose 섭취가 질환 악화와 연관된다는 역학적 근거는 존재하였으나, 실제로 어떤 생물학적 경로를 통해 hepatic fibrosis로 이어지는지는 명확하지 않았습니다. 본 연구는 gut-liver axis에 주목하여, 장내미생물이 생성하는 metabolite가 질환 진행의 핵심 매개체일 가능성을 검증하고자 하였습니다.

대규모 UK Biobank 분석에서 총 당 및 fructose 섭취량이 높을수록 liver disease 발생 및 간 관련 사망 위험이 증가하는 경향이 확인되었습니다. 이어진 metagenomics 분석에서는 MASH 단계 환자에서 장내미생물의 fermentation pathway가 acetaldehyde 생성 방향으로 재편되는 현상이 관찰되었습니다. 임상 분변을 이용한 in vitro 실험에서도 MASH 환자 분변이 fructose를 더 많은 acetaldehyde로 전환함이 입증되었으며, 해당 물질은 hepatic stellate cell을 자극하여 MMP7 expression을 증가시키고 fibrosis를 촉진하는 기전이 제시되었습니다. 나아가 acetaldehyde 제거 능력을 강화한 engineered probiotics를 투여하였을 때, 동물 모델에서 hepatic fibrosis와 inflammation 지표가 유의하게 감소하는 결과를 보였습니다.

본 연구는 과도한 당 섭취가 단순히 lipid accumulation을 넘어서, 장내미생물 유래 acetaldehyde를 매개로 hepatic fibrosis를 직접 촉진한다는 기전적 연결고리를 제시하였습니다. 특히 acetaldehyde-MMP7-hepatic stellate cell axis를 중심으로 한 분자적 경로를 규명하고, 이를 microbiome 기반 치료 전략으로 역전시킬 수 있음을 전임상 수준에서 입증하였다는 점에서 학문적·임상적 의의가 큽니다. 이는 MASH 치료에서 dietary intervention과 gut microbiome modulation을 결합한 precision medicine 전략의 가능성을 제시하는 중요한 근거가 될 수 있습니다.

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
1. 반드시 4개 문단(한 줄 개요 / 연구 배경 / 핵심 발견 / 의의)으로만 작성하세요.
2. 마크다운 헤딩(#, ##, ###), 불릿 포인트(-, *), 번호 목록(1., 2.)은 절대 사용하지 마세요. 순수 산문체만 사용하세요.
3. 모든 전문 용어는 영어 그대로 쓰세요:
   - "proteogenomics" (O) / "프로테오지노믹스" (X)
   - "spatial transcriptomics" (O) / "공간 전사체" (X)
   - "single-cell RNA-seq" (O) / "단일세포" (X)
   - "fibrosis" (O) / "섬유화" (X)
   - "hepatic stellate cell" (O) / "간 성상세포" (X)
4. 초록과 본문에 있는 내용만 쓰세요. 없는 내용을 지어내지 마세요.
5. 제공된 텍스트의 품질, 완전성, 잘림 여부에 대해 절대 언급하지 마세요.

위 예시처럼 서술형 산문체로 요약해주세요.
"""

# Simplified prompt when only abstract is available (NO PDF)
SUMMARIZE_PROMPT_ABSTRACT_ONLY = """다음 논문을 초록만 기반으로 한국어로 요약해주세요.

## 출력 형식 (반드시 이 4문단 구조를 따르세요):

문단1 - 한 줄 개요: 이 논문이 무엇을 한 연구인지 1문장으로 요약.
문단2 - 연구 배경: 질환/분야의 맥락, 기존에 알려진 사실, 해결되지 않은 문제, 이 연구의 동기.
문단3 - 핵심 발견: 연구진이 수행한 분석과 구체적 결과. 어떤 방법을 썼고, 무엇을 발견했는지.
문단4 - 의의: 이 연구가 해당 분야에 미치는 영향, 임상적/학문적 함의, 향후 전망.

각 문단 사이에 반드시 빈 줄을 넣으세요 (총 4개 문단, 3개 빈 줄).
마크다운 헤딩(#), 불릿(-), 번호(1.)는 절대 사용하지 마세요.

## 예시:

장내미생물 대사 분석을 통해 MASH fibrosis 기전을 보여준 연구입니다.

MASLD은 일부 환자에서 염증과 fibrosis를 동반한 MASH으로 진행하며, 이 단계에서 cirrhosis와 hepatocellular carcinoma 위험이 크게 증가합니다. 그동안 과도한 fructose 섭취가 질환 악화와 연관된다는 역학적 근거는 존재하였으나, 실제로 어떤 생물학적 경로를 통해 hepatic fibrosis로 이어지는지는 명확하지 않았습니다. 본 연구는 gut-liver axis에 주목하여, 장내미생물이 생성하는 metabolite가 질환 진행의 핵심 매개체일 가능성을 검증하고자 하였습니다.

대규모 UK Biobank 분석에서 총 당 및 fructose 섭취량이 높을수록 liver disease 발생 위험이 증가하는 경향이 확인되었습니다. Metagenomics 분석에서는 MASH 환자에서 장내미생물의 fermentation pathway가 acetaldehyde 생성 방향으로 재편되는 현상이 관찰되었으며, 해당 물질은 hepatic stellate cell을 자극하여 MMP7 expression을 증가시키고 fibrosis를 촉진하는 기전이 제시되었습니다. Engineered probiotics 투여 시 동물 모델에서 hepatic fibrosis가 유의하게 감소하였습니다.

본 연구는 장내미생물 유래 acetaldehyde를 매개로 hepatic fibrosis가 촉진된다는 기전적 연결고리를 제시하였으며, microbiome 기반 치료 전략의 가능성을 전임상 수준에서 입증하였다는 점에서 학문적·임상적 의의가 큽니다.

---

## 요약할 논문:

- 제목: {title}
- 저널: {journal}
- 저자: {authors}

## 초록
{abstract}

---

**절대 규칙 (MUST FOLLOW):**
1. 반드시 4개 문단(한 줄 개요 / 연구 배경 / 핵심 발견 / 의의)으로만 작성하세요.
2. 마크다운 헤딩(#, ##, ###), 불릿 포인트(-, *), 번호 목록(1., 2.)은 절대 사용하지 마세요. 순수 산문체만 사용하세요.
3. 모든 전문 용어는 영어 그대로 쓰세요:
   - "proteogenomics" (O) / "프로테오지노믹스" (X)
   - "spatial transcriptomics" (O) / "공간 전사체" (X)
   - "single-cell RNA-seq" (O) / "단일세포" (X)
4. 초록에 있는 내용만 쓰세요. 없는 내용을 지어내지 마세요.
5. 제공된 텍스트의 품질, 완전성, 잘림 여부에 대해 절대 언급하지 마세요.

위 예시처럼 서술형 산문체로 요약해주세요.
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

        # Ensure prose paragraphs are separated by blank lines
        summary = ensure_paragraph_breaks(summary)

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
**원문 해석**: stACN의 spatially resolved transcriptomics 데이터 분석을 위한 전체 workflow를 나타낸 모식도. (A) Input data 처리 단계에서 spatial gene expression matrix와 좌표 정보가 모델에 입력된다. (B) Graph noise model이 cell-cell 관계 정보를 학습하여 dual cell network을 구성한다. (C) Joint tensor decomposition을 통해 denoised expression과 spatial domain identification 결과가 출력된다.
**핵심 내용**: Spatially resolved transcriptomics 실험 workflow와 stACN model의 구조를 보여준다.
**세부 설명**:
- Panel A: stACN model의 전체 workflow. Input으로 SRT data를 받아 denoising과 spatial domain identification을 수행한다.
- Panel B: Graph noise model을 통한 dual cell network 학습 과정.
- Panel C: Joint tensor decomposition을 통한 cell feature 추출.

#### Figure 2: Spatial domain identification 결과
**원문 해석**: DLPFC 데이터셋에서 stACN과 기존 방법(BayesSpace, SpaGCN, STAGATE 등)의 spatial domain identification 성능을 비교한 결과. (A) 각 방법의 spatial domain 예측 결과를 ground truth annotation과 시각적으로 비교한 image. (B) 모든 슬라이스에 대한 Adjusted Rand Index (ARI) score의 boxplot으로 stACN이 모든 데이터셋에서 가장 높은 ARI score를 기록하였다.
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
4. **원문 해석** 필드는 위에 주어진 Figure Legend 원문을 한국어로 자연스럽게 번역/해석한 내용입니다.
   - Legend 원문에 있는 정보만 사용하세요. 새로운 정보를 추가하거나 추측하지 마세요.
   - 전문 용어는 영어 그대로 유지하면서 한국어 문장으로 풀어 쓰세요.
   - Legend가 없거나 부족하면 "(원문 legend 없음)"으로만 표기하고 절대 추측해서 채우지 마세요.
5. 각 Figure 항목은 반드시 **원문 해석** → **핵심 내용** → **세부 설명** 순서를 지키세요.

위 예시처럼 세 필드를 순서대로 채워 Figure를 순서대로 설명해주세요.
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
