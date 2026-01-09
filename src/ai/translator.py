"""Abstract translation for English study."""

import re
from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


TRANSLATION_SYSTEM_PROMPT = """당신은 생물정보학(bioinformatics), 암 연구(cancer research), 인공지능(AI/ML) 분야 전문 번역가입니다.
학술 논문의 abstract를 문장 단위로 정확하고 자연스럽게 한국어로 번역해주세요.
전문 용어는 적절한 한국어 번역과 함께 영어 원어를 괄호 안에 병기하세요.
과학적 정확성을 유지하면서 읽기 쉬운 한국어로 번역해주세요."""

TRANSLATION_PROMPT_TEMPLATE = """다음 영어 논문 abstract를 문장 단위로 한국어로 번역해주세요.

## Abstract
{abstract}

---

## 중요 지침

**문장 분리 규칙:**
1. 영어 문장은 반드시 완전한 형태로 유지하세요 (절대로 문장 중간에서 끊지 마세요!)
2. 마침표(.), 물음표(?), 느낌표(!)로 끝나는 완전한 문장을 기준으로 분리
3. 콤마나 세미콜론으로 연결된 복합문장은 하나의 문장으로 처리
4. "e.g.", "i.e.", "et al.", "vs." 등의 약어 뒤 마침표는 문장 끝이 아님

**번역 규칙:**
1. 전문 용어: "단일세포 RNA 시퀀싱(single-cell RNA-seq)" 형식
2. 약어는 처음 등장 시 풀어서 설명: "IDH(isocitrate dehydrogenase, 이소시트르산 탈수소효소)"
3. 유전자명, 단백질명 등은 원어 그대로: "p53 유전자", "BRCA1 돌연변이"
4. 통계 수치와 p-value는 원문 그대로 유지
5. 자연스러운 한국어 문장이 되도록 의역 가능 (의미 왜곡 금지)

## 출력 형식 (정확히 따라주세요)

[EN] 첫 번째 완전한 영어 문장.
[KO] 첫 번째 문장의 한국어 번역.

[EN] 두 번째 완전한 영어 문장.
[KO] 두 번째 문장의 한국어 번역.

(모든 문장에 대해 반복)
"""


class AbstractTranslator:
    """Translate abstract line by line for English study."""

    def __init__(self, llm_client: LLMClient):
        """
        Initialize translator.

        Args:
            llm_client: LLM client for translation
        """
        self.llm = llm_client

    def translate(self, abstract: str) -> list[dict[str, str]]:
        """
        Translate abstract line by line.

        Args:
            abstract: English abstract text

        Returns:
            List of {"en": english_sentence, "ko": korean_translation}
        """
        if not abstract:
            return []

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(abstract=abstract)
        response = self.llm.generate(prompt, system=TRANSLATION_SYSTEM_PROMPT)

        return self._parse_translation(response)

    def _parse_translation(self, response: str) -> list[dict[str, str]]:
        """Parse LLM response into sentence pairs."""
        pairs = []
        current_en = None
        current_ko = None

        lines = response.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for [EN] prefix
            if line.startswith('[EN]'):
                # Save previous pair if exists
                if current_en and current_ko:
                    pairs.append({"en": current_en, "ko": current_ko})
                current_en = line[4:].strip()
                current_ko = None

            # Check for [KO] prefix
            elif line.startswith('[KO]'):
                current_ko = line[4:].strip()

            # Handle continuation lines
            elif current_ko is None and current_en:
                # Might be continuation of EN
                if not any(line.startswith(p) for p in ['[EN]', '[KO]', '---']):
                    current_en += ' ' + line
            elif current_ko:
                # Might be continuation of KO
                if not any(line.startswith(p) for p in ['[EN]', '[KO]', '---']):
                    current_ko += ' ' + line

        # Add last pair
        if current_en and current_ko:
            pairs.append({"en": current_en, "ko": current_ko})

        return pairs

    def translate_paper(self, paper: Paper) -> list[dict[str, str]]:
        """
        Translate paper's abstract.

        Args:
            paper: Paper object

        Returns:
            List of sentence pairs
        """
        return self.translate(paper.abstract)

    def format_for_display(
        self,
        translations: list[dict[str, str]],
        format_type: str = "markdown"
    ) -> str:
        """
        Format translations for display.

        Args:
            translations: List of translation pairs
            format_type: "markdown", "html", or "plain"

        Returns:
            Formatted string
        """
        if format_type == "markdown":
            lines = []
            for i, pair in enumerate(translations, 1):
                lines.append(f"**{i}.** {pair['en']}")
                lines.append(f"")
                lines.append(f"> {pair['ko']}")
                lines.append("")
            return "\n".join(lines)

        elif format_type == "html":
            lines = ["<div class='translation'>"]
            for i, pair in enumerate(translations, 1):
                lines.append(f"  <div class='sentence-pair'>")
                lines.append(f"    <p class='en'><strong>{i}.</strong> {pair['en']}</p>")
                lines.append(f"    <p class='ko'>{pair['ko']}</p>")
                lines.append(f"  </div>")
            lines.append("</div>")
            return "\n".join(lines)

        else:  # plain
            lines = []
            for i, pair in enumerate(translations, 1):
                lines.append(f"{i}. [EN] {pair['en']}")
                lines.append(f"   [KO] {pair['ko']}")
                lines.append("")
            return "\n".join(lines)


class SimpleTranslator:
    """Simple sentence splitter for cases without LLM."""

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
