"""Abstract translation for English study."""

import re
from typing import Optional

from .llm_client import LLMClient
from .summarizer import remove_non_korean_foreign_chars
from ..models import Paper


TRANSLATION_SYSTEM_PROMPT = """You are a translator specializing in biomedical papers. Translate English sentences to natural Korean.

RULES:
1. Keep ALL technical terms in English:
   - Cell names: melanocyte, fibroblast, macrophage, T cell, B cell, neuron
   - Anatomy: neural crest, epidermis, dermis, adipose tissue
   - Molecules: RNA, DNA, protein, BMP, ID1, p53, BRAF
   - Methods: single-cell RNA-seq, ATAC-seq, UMAP, t-SNE, fMRI
   - NEVER transliterate: "melanocyte" stays as "melanocyte" (NOT "멜라노사이트" or "며느기")
2. Use simple, natural Korean grammar
3. Output format must be exactly: [EN] English [KO] Korean"""

TRANSLATION_PROMPT_TEMPLATE = """Translate this abstract sentence by sentence.

Abstract:
{abstract}

Output format (follow exactly):

[EN] First English sentence.
[KO] 첫 번째 문장의 한국어 번역.

[EN] Second English sentence.
[KO] 두 번째 문장의 한국어 번역.

CRITICAL Rules:
- Keep ALL technical terms in English:
  * Cell names: melanocyte, fibroblast, neuron, T cell → Keep as English
  * Anatomy: neural crest, epidermis → Keep as English
  * Methods: single-cell RNA-seq, ATAC-seq → Keep as English
  * Molecules: BMP, ID1, BRAF → Keep as English
- NEVER transliterate cell names (NO "멜라노사이트", NO "며느기")
- Write natural Korean sentences
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

    def _remove_instruction_echoes(self, text: str) -> str:
        """Remove LLM instruction echoes from translation response."""
        # Patterns that indicate instruction text being echoed back
        instruction_patterns = [
            r'\*\*이번 번역의 중요 지침\*\*.*?(?=\[EN\]|\[KO\]|$)',
            r'\*\*번역 규칙\*\*.*?(?=\[EN\]|\[KO\]|$)',
            r'\*\*문장 분리 규칙\*\*.*?(?=\[EN\]|\[KO\]|$)',
            r'\*\*절대 준수 규칙\*\*.*?(?=\[EN\]|\[KO\]|$)',
            r'\*\*출력 형식\*\*.*?(?=\[EN\]|\[KO\]|$)',
            r'##\s*중요 지침.*?(?=\[EN\]|\[KO\]|$)',
            r'##\s*출력 형식.*?(?=\[EN\]|\[KO\]|$)',
            # Numbered instruction lines
            r'\d+\.\s*전문 용어는 영어 원문[^\n]*\n?',
            r'\d+\.\s*유전자명[^\n]*\n?',
            r'\d+\.\s*통계 수치[^\n]*\n?',
            r'\d+\.\s*자연스러운 한국어[^\n]*\n?',
            r'\d+\.\s*절대로 한자[^\n]*\n?',
            r'\d+\.\s*한자[^\n]*금지[^\n]*\n?',
            # Alternative format markers that should not appear
            r'\*\*원문:\*\*',
            r'\*\*번역 결과:\*\*',
            r'\*\*번역:\*\*',
            # LLM chatter/noise to remove
            r'Let me know if you\'d like.*$',
            r'I hope this helps.*$',
            r'Please let me know.*$',
            r'Feel free to ask.*$',
            r'Is there anything else.*$',
            r'I\'ll continue.*$',
            r'\.\.\.\s*I\'ll.*$',
            r'Would you like me to.*$',
        ]

        result = text
        for pattern in instruction_patterns:
            result = re.sub(pattern, '', result, flags=re.DOTALL | re.MULTILINE)

        # Clean up multiple newlines
        result = re.sub(r'\n{3,}', '\n\n', result)

        return result.strip()

    def _parse_translation(self, response: str) -> list[dict[str, str]]:
        """Parse LLM response into sentence pairs."""
        pairs = []
        current_en = None
        current_ko = None

        # Remove LLM instruction echoes from response
        response = self._remove_instruction_echoes(response)

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

        # Post-process: remove Chinese/Japanese/Cyrillic characters from Korean translations
        for pair in pairs:
            if 'ko' in pair:
                pair['ko'] = remove_non_korean_foreign_chars(pair['ko'])

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
