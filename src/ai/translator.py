"""Abstract translation for English study."""

import re
from typing import Optional

from .llm_client import LLMClient
from ..models import Paper


TRANSLATION_SYSTEM_PROMPT = """당신은 생물정보학/AI 분야의 영어-한국어 번역 전문가입니다.
학술 논문의 abstract를 문장 단위로 정확하게 번역해주세요.
전문 용어는 적절한 한국어 번역과 함께 영어 원어를 괄호 안에 병기하세요."""

TRANSLATION_PROMPT_TEMPLATE = """다음 영어 abstract를 문장 단위로 한국어로 번역해주세요.

## Abstract
{abstract}

---

각 영어 문장과 그에 해당하는 한국어 번역을 다음 형식으로 출력해주세요:

[EN] 영어 문장 1
[KO] 한국어 번역 1

[EN] 영어 문장 2
[KO] 한국어 번역 2

...

주의사항:
1. 문장을 정확히 구분하세요 (마침표, 물음표 등 기준)
2. 전문 용어는 "단일세포 RNA 시퀀싱(single-cell RNA-seq)" 형식으로 번역
3. 약어는 처음 등장할 때 풀어서 설명
4. 의역보다 직역을 우선하되, 자연스러운 한국어로 작성
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
