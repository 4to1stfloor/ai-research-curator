"""PDF parser for extracting text and figures."""

import os
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from ..models import Paper


class PDFParser:
    """Parse PDF files to extract text and figures."""

    def __init__(self, figures_dir: str | Path):
        """
        Initialize PDF parser.

        Args:
            figures_dir: Directory to save extracted figures
        """
        self.figures_dir = Path(figures_dir)
        self.figures_dir.mkdir(parents=True, exist_ok=True)

    def extract_text(self, pdf_path: str | Path) -> str:
        """
        Extract all text from PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        try:
            doc = fitz.open(pdf_path)
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text())

            doc.close()
            return "\n".join(text_parts)

        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""

    def extract_figures(
        self,
        pdf_path: str | Path,
        paper_id: str,
        min_width: int = 100,
        min_height: int = 100
    ) -> list[str]:
        """
        Extract figures/images from PDF.

        Args:
            pdf_path: Path to PDF file
            paper_id: Unique identifier for naming
            min_width: Minimum image width to extract
            min_height: Minimum image height to extract

        Returns:
            List of paths to extracted images
        """
        extracted_paths = []

        try:
            doc = fitz.open(pdf_path)

            # Create paper-specific directory
            paper_dir = self.figures_dir / self._sanitize_id(paper_id)
            paper_dir.mkdir(exist_ok=True)

            img_index = 0

            for page_num, page in enumerate(doc):
                # Get images on this page
                image_list = page.get_images(full=True)

                for img_info in image_list:
                    xref = img_info[0]

                    try:
                        # Extract image
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # Get image dimensions
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)

                        # Filter small images (logos, icons, etc.)
                        if width < min_width or height < min_height:
                            continue

                        # Save image
                        img_filename = f"fig_{page_num + 1}_{img_index}.{image_ext}"
                        img_path = paper_dir / img_filename

                        with open(img_path, "wb") as f:
                            f.write(image_bytes)

                        extracted_paths.append(str(img_path))
                        img_index += 1

                    except Exception as e:
                        print(f"Error extracting image {xref}: {e}")
                        continue

            doc.close()
            print(f"Extracted {len(extracted_paths)} figures from {pdf_path}")

        except Exception as e:
            print(f"Error processing PDF: {e}")

        return extracted_paths

    def extract_sections(self, text: str) -> dict[str, str]:
        """
        Extract common paper sections from text.

        Args:
            text: Full paper text

        Returns:
            Dictionary of section name to content
        """
        sections = {}

        # Common section patterns
        section_patterns = [
            (r"abstract", "abstract"),
            (r"introduction", "introduction"),
            (r"background", "background"),
            (r"methods?|materials?\s*(?:and|&)\s*methods?", "methods"),
            (r"results?", "results"),
            (r"discussion", "discussion"),
            (r"conclusion", "conclusion"),
            (r"references?|bibliography", "references"),
            (r"acknowledgements?", "acknowledgements"),
            (r"supplementary|supporting\s*information", "supplementary"),
        ]

        # Try to find sections
        text_lower = text.lower()

        for pattern, section_name in section_patterns:
            # Find section header
            matches = list(re.finditer(
                rf'\n\s*({pattern})\s*\n',
                text_lower,
                re.IGNORECASE
            ))

            if matches:
                start = matches[0].end()

                # Find next section
                end = len(text)
                for next_pattern, _ in section_patterns:
                    next_matches = list(re.finditer(
                        rf'\n\s*({next_pattern})\s*\n',
                        text_lower[start:],
                        re.IGNORECASE
                    ))
                    if next_matches:
                        potential_end = start + next_matches[0].start()
                        if potential_end < end:
                            end = potential_end

                sections[section_name] = text[start:end].strip()

        return sections

    def _sanitize_id(self, paper_id: str) -> str:
        """Sanitize paper ID for use as directory name."""
        safe = re.sub(r'[<>:"/\\|?*]', '', paper_id)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:100]

    def parse_paper(
        self,
        paper: Paper,
        extract_figures: bool = True
    ) -> dict:
        """
        Parse a paper PDF.

        Args:
            paper: Paper object with local_pdf_path set
            extract_figures: Whether to extract figures

        Returns:
            Dictionary with extracted content
        """
        if not paper.local_pdf_path or not Path(paper.local_pdf_path).exists():
            return {
                "text": "",
                "sections": {},
                "figures": []
            }

        # Extract text
        text = self.extract_text(paper.local_pdf_path)

        # Extract sections
        sections = self.extract_sections(text)

        # Extract figures
        figures = []
        if extract_figures:
            paper_id = paper.doi or paper.pmid or paper.title[:50]
            figures = self.extract_figures(paper.local_pdf_path, paper_id)
            paper.extracted_figures = figures

        return {
            "text": text,
            "sections": sections,
            "figures": figures
        }


class AbstractExtractor:
    """Extract abstract from various sources."""

    @staticmethod
    def extract(paper: Paper, pdf_text: Optional[str] = None) -> str:
        """
        Extract abstract from paper.

        Priority:
        1. Paper.abstract (from API/RSS)
        2. PDF text (if available)

        Args:
            paper: Paper object
            pdf_text: Optional full PDF text

        Returns:
            Abstract text
        """
        # Use existing abstract if available
        if paper.abstract:
            return paper.abstract

        # Try to extract from PDF
        if pdf_text:
            # Look for abstract section
            abstract_match = re.search(
                r'abstract\s*\n(.+?)(?=\n\s*(?:introduction|background|keywords))',
                pdf_text,
                re.IGNORECASE | re.DOTALL
            )
            if abstract_match:
                return abstract_match.group(1).strip()

        return ""
