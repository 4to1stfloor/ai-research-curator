"""Obsidian markdown exporter."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Paper, ProcessedPaper


PAPER_NOTE_TEMPLATE = """---
title: "{title}"
authors: {authors}
journal: "{journal}"
date: {pub_date}
doi: "{doi}"
url: "{url}"
tags: [{tags}]
created: {created}
type: paper
---

# {title}

## 메타데이터
- **저널**: {journal}
- **출판일**: {pub_date}
- **저자**: {authors_str}
- **DOI**: [{doi}]({doi_url})
- **링크**: [논문 보기]({url})

## 한 줄 요약
{one_line_summary}

---

## 📝 요약 (Summary)

{summary}

---

## 📖 Abstract 영-한 번역

{translation}

---

## 📊 Figures

{figures}

---

## 🔀 연구 흐름도

{diagram}

---

## 관련 논문
-

## 메모
-

"""

DAILY_DIGEST_TEMPLATE = """---
title: "논문 다이제스트 - {date}"
date: {date}
type: digest
papers: {paper_count}
tags: [논문, 다이제스트, {year}년{month}월]
---

# 논문 다이제스트 - {date}

> {paper_count}개의 논문을 요약했습니다.

## 논문 목록

{paper_list}

---

## 상세 내용

{paper_details}
"""


class ObsidianExporter:
    """Export processed papers to Obsidian markdown."""

    def __init__(self, vault_path: str | Path):
        """
        Initialize Obsidian exporter.

        Args:
            vault_path: Path to Obsidian vault (or subfolder)
        """
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Create subfolders
        self.papers_dir = self.vault_path / "papers"
        self.digests_dir = self.vault_path / "digests"
        self.figures_dir = self.vault_path / "figures"

        self.papers_dir.mkdir(exist_ok=True)
        self.digests_dir.mkdir(exist_ok=True)
        self.figures_dir.mkdir(exist_ok=True)

    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title."""
        import re
        # Remove invalid characters
        safe = re.sub(r'[<>:"/\\|?*\[\]#^]', '', title)
        # Replace multiple spaces with single underscore
        safe = re.sub(r'\s+', ' ', safe).strip()
        # Limit length
        return safe[:100]

    def _format_tags(self, paper: Paper) -> str:
        """Generate tags for paper."""
        tags = ['논문']

        # Add journal as tag
        if paper.journal:
            journal_tag = paper.journal.replace(' ', '_')
            tags.append(journal_tag)

        # Add keywords as tags
        for kw in paper.keywords[:5]:
            kw_tag = kw.replace(' ', '_').replace('-', '_')
            tags.append(kw_tag)

        # Add source
        tags.append(paper.source.value)

        return ', '.join(tags)

    def _format_authors_yaml(self, authors: list[str]) -> str:
        """Format authors for YAML frontmatter."""
        if not authors:
            return "[]"
        authors_escaped = [f'"{a}"' for a in authors[:10]]
        return '[' + ', '.join(authors_escaped) + ']'

    def _format_translation_md(self, translations: list[dict]) -> str:
        """Format translation for markdown."""
        if not translations:
            return "*번역 없음*"

        lines = []
        for i, pair in enumerate(translations, 1):
            lines.append(f"**{i}.** {pair.get('en', '')}")
            lines.append(f"> {pair.get('ko', '')}")
            lines.append("")

        return '\n'.join(lines)

    def _format_figures_md(self, figures: list[str], paper_id: str) -> str:
        """Format figures for markdown and copy to vault."""
        if not figures:
            return "*그림 없음*"

        lines = []
        paper_figures_dir = self.figures_dir / self._sanitize_filename(paper_id)
        paper_figures_dir.mkdir(exist_ok=True)

        for i, fig_path in enumerate(figures[:6], 1):
            try:
                # Copy figure to vault
                src = Path(fig_path)
                if src.exists():
                    dst = paper_figures_dir / src.name
                    import shutil
                    shutil.copy2(src, dst)

                    # Create relative path for Obsidian
                    rel_path = dst.relative_to(self.vault_path)
                    lines.append(f"![[{rel_path}|Figure {i}]]")
                    lines.append("")
            except Exception as e:
                print(f"Error copying figure: {e}")

        return '\n'.join(lines) if lines else "*그림 없음*"

    def _extract_one_line_summary(self, summary: str) -> str:
        """Extract one-line summary from full summary."""
        # Look for "한 줄 요약" section
        if "한 줄 요약" in summary:
            start = summary.find("한 줄 요약")
            end = summary.find("\n", start + 10)
            if end > start:
                line = summary[start:end].strip()
                # Remove header markers
                line = line.replace("### ", "").replace("한 줄 요약", "").strip()
                if line:
                    return line

        # Fallback: first sentence of summary
        sentences = summary.split('.')
        if sentences:
            return sentences[0].strip() + "."

        return ""

    def export_paper(
        self,
        processed_paper: ProcessedPaper,
        diagram_info: Optional[dict] = None
    ) -> str:
        """
        Export a single paper to Obsidian note.

        Args:
            processed_paper: Processed paper
            diagram_info: Optional diagram information

        Returns:
            Path to created note
        """
        paper = processed_paper.paper
        diagram_info = diagram_info or {}

        # Create filename
        filename = self._sanitize_filename(paper.title) + ".md"
        filepath = self.papers_dir / filename

        # Prepare content
        pub_date = paper.publication_date.strftime("%Y-%m-%d") if paper.publication_date else "unknown"
        doi_url = f"https://doi.org/{paper.doi}" if paper.doi else paper.url

        # Format diagram
        diagram_content = "*다이어그램 없음*"
        if diagram_info.get('mermaid_code'):
            diagram_content = f"```mermaid\n{diagram_info['mermaid_code']}\n```"

        content = PAPER_NOTE_TEMPLATE.format(
            title=paper.title.replace('"', '\\"'),
            authors=self._format_authors_yaml(paper.authors),
            journal=paper.journal,
            pub_date=pub_date,
            doi=paper.doi or "",
            url=paper.url,
            tags=self._format_tags(paper),
            created=datetime.now().strftime("%Y-%m-%d %H:%M"),
            authors_str=", ".join(paper.authors[:5]) + ("..." if len(paper.authors) > 5 else ""),
            doi_url=doi_url,
            one_line_summary=self._extract_one_line_summary(processed_paper.summary_korean),
            summary=processed_paper.summary_korean,
            translation=self._format_translation_md(processed_paper.abstract_translation),
            figures=self._format_figures_md(processed_paper.figures, paper.doi or paper.title),
            diagram=diagram_content
        )

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Exported: {filepath}")
        return str(filepath)

    def export_daily_digest(
        self,
        processed_papers: list[ProcessedPaper],
        diagrams: Optional[dict] = None
    ) -> str:
        """
        Export daily digest note.

        Args:
            processed_papers: List of processed papers
            diagrams: Optional dict of {paper_id: diagram_info}

        Returns:
            Path to created digest note
        """
        diagrams = diagrams or {}
        now = datetime.now()

        # Create filename
        filename = f"digest_{now.strftime('%Y%m%d')}.md"
        filepath = self.digests_dir / filename

        # Generate paper list
        paper_list_items = []
        for i, pp in enumerate(processed_papers, 1):
            paper_filename = self._sanitize_filename(pp.paper.title)
            one_line = self._extract_one_line_summary(pp.summary_korean)
            paper_list_items.append(
                f"{i}. [[papers/{paper_filename}|{pp.paper.title[:60]}...]]\n   - {one_line[:100]}"
            )

        # Generate paper details (brief)
        paper_details = []
        for i, pp in enumerate(processed_papers, 1):
            paper_filename = self._sanitize_filename(pp.paper.title)
            paper_details.append(f"""
### {i}. {pp.paper.title}

- **저널**: {pp.paper.journal}
- **상세**: [[papers/{paper_filename}|전체 보기]]

{self._extract_one_line_summary(pp.summary_korean)}

---
""")

        content = DAILY_DIGEST_TEMPLATE.format(
            date=now.strftime("%Y-%m-%d"),
            year=now.year,
            month=now.month,
            paper_count=len(processed_papers),
            paper_list='\n'.join(paper_list_items),
            paper_details='\n'.join(paper_details)
        )

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Exported digest: {filepath}")
        return str(filepath)

    def export_all(
        self,
        processed_papers: list[ProcessedPaper],
        diagrams: Optional[dict] = None,
        create_digest: bool = True
    ) -> dict:
        """
        Export all papers and optionally create digest.

        Args:
            processed_papers: List of processed papers
            diagrams: Optional dict of {paper_id: diagram_info}
            create_digest: Whether to create daily digest

        Returns:
            Dict with paper_paths and digest_path
        """
        diagrams = diagrams or {}
        result = {"paper_paths": [], "digest_path": None}

        # Export individual papers
        for pp in processed_papers:
            paper_id = pp.paper.doi or pp.paper.title
            diagram_info = diagrams.get(paper_id)

            path = self.export_paper(pp, diagram_info)
            result["paper_paths"].append(path)

        # Create digest
        if create_digest:
            result["digest_path"] = self.export_daily_digest(processed_papers, diagrams)

        return result
