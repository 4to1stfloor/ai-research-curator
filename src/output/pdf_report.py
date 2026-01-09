"""PDF report generator."""

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Paper, ProcessedPaper


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>논문 다이제스트 - {date}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
            line-height: 1.8;
            color: #333;
            max-width: 210mm;
            margin: 0 auto;
            padding: 20mm;
            background: white;
        }}

        h1 {{
            font-size: 24pt;
            color: #1a365d;
            border-bottom: 3px solid #3182ce;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}

        h2 {{
            font-size: 16pt;
            color: #2c5282;
            margin-top: 40px;
            margin-bottom: 15px;
            padding-left: 10px;
            border-left: 4px solid #3182ce;
        }}

        h3 {{
            font-size: 13pt;
            color: #2d3748;
            margin-top: 20px;
            margin-bottom: 10px;
        }}

        .paper {{
            margin-bottom: 50px;
            padding: 20px;
            background: #f7fafc;
            border-radius: 8px;
            page-break-inside: avoid;
        }}

        .paper-title {{
            font-size: 14pt;
            font-weight: bold;
            color: #1a365d;
            margin-bottom: 10px;
        }}

        .paper-meta {{
            font-size: 10pt;
            color: #718096;
            margin-bottom: 15px;
        }}

        .paper-meta span {{
            margin-right: 15px;
        }}

        .summary {{
            background: white;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
        }}

        .translation {{
            background: white;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
        }}

        .sentence-pair {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px dashed #e2e8f0;
        }}

        .sentence-pair:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}

        .en {{
            font-size: 11pt;
            color: #2d3748;
            margin-bottom: 5px;
        }}

        .ko {{
            font-size: 11pt;
            color: #4a5568;
            padding-left: 15px;
            border-left: 2px solid #cbd5e0;
        }}

        .figures {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 15px 0;
        }}

        .figure {{
            max-width: 45%;
            text-align: center;
        }}

        .figure img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #e2e8f0;
            border-radius: 5px;
        }}

        .figure-caption {{
            font-size: 9pt;
            color: #718096;
            margin-top: 5px;
        }}

        .diagram {{
            background: white;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
            text-align: center;
        }}

        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 9pt;
            color: #a0aec0;
            text-align: center;
        }}

        .toc {{
            background: #edf2f7;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}

        .toc-title {{
            font-size: 14pt;
            font-weight: bold;
            margin-bottom: 15px;
        }}

        .toc-item {{
            margin: 8px 0;
            padding-left: 15px;
        }}

        .toc-item a {{
            color: #2c5282;
            text-decoration: none;
        }}

        @media print {{
            body {{
                padding: 15mm;
            }}

            .paper {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <h1>논문 다이제스트</h1>
    <p style="color: #718096; margin-bottom: 20px;">{date} | {paper_count}개 논문</p>

    <div class="toc">
        <div class="toc-title">목차</div>
        {toc_items}
    </div>

    {paper_sections}

    <div class="footer">
        <p>자동 생성됨 by Paper Digest AI | {date}</p>
    </div>
</body>
</html>
"""

PAPER_SECTION_TEMPLATE = """
<div class="paper" id="paper-{index}">
    <div class="paper-title">{index}. {title}</div>
    <div class="paper-meta">
        <span>📚 {journal}</span>
        <span>📅 {pub_date}</span>
        <span>🔗 <a href="{url}">{doi}</a></span>
    </div>

    <h3>📝 요약 (Summary)</h3>
    <div class="summary">
        {summary}
    </div>

    <h3>📖 Abstract 영-한 번역</h3>
    <div class="translation">
        {translation}
    </div>

    {figures_section}

    {figure_explanation_section}
</div>
"""


class PDFReportGenerator:
    """Generate PDF reports from processed papers."""

    def __init__(self, output_dir: str | Path):
        """
        Initialize PDF generator.

        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_summary(self, summary: str) -> str:
        """Format summary for HTML with proper markdown conversion."""
        import re

        # Convert markdown-like formatting to HTML
        lines = summary.split('\n')
        html_lines = []
        in_list = False

        for line in lines:
            line = line.strip()

            # Convert inline **bold** to <strong>
            line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line)

            # Convert inline *italic* to <em>
            line = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', line)

            if not line:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append('<br>')
            elif line.startswith('### '):
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<h4>{line[4:]}</h4>')
            elif line.startswith('## '):
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<h3>{line[3:]}</h3>')
            elif line.startswith('- '):
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                html_lines.append(f'<li>{line[2:]}</li>')
            elif re.match(r'^\d+\.', line):
                # Numbered list
                if not in_list:
                    html_lines.append('<ol>')
                    in_list = True
                content = re.sub(r'^\d+\.\s*', '', line)
                html_lines.append(f'<li>{content}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<p>{line}</p>')

        if in_list:
            html_lines.append('</ul>')

        return '\n'.join(html_lines)

    def _format_translation(self, translations: list[dict]) -> str:
        """Format translation pairs for HTML."""
        html_parts = []

        for i, pair in enumerate(translations, 1):
            html_parts.append(f'''
            <div class="sentence-pair">
                <p class="en"><strong>{i}.</strong> {pair.get('en', '')}</p>
                <p class="ko">{pair.get('ko', '')}</p>
            </div>
            ''')

        return '\n'.join(html_parts)

    def _format_figures(self, figures: list[str]) -> str:
        """Format figure paths for HTML."""
        if not figures:
            return ""

        html_parts = ['<h3>📊 Figures</h3>', '<div class="figures">']

        for i, fig_path in enumerate(figures[:6], 1):  # Limit to 6 figures
            try:
                # Embed image as base64
                with open(fig_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()

                ext = Path(fig_path).suffix.lower()
                mime = 'image/png' if ext == '.png' else 'image/jpeg'

                html_parts.append(f'''
                <div class="figure">
                    <img src="data:{mime};base64,{img_data}" alt="Figure {i}">
                    <p class="figure-caption">Figure {i}</p>
                </div>
                ''')
            except Exception as e:
                print(f"Error embedding figure {fig_path}: {e}")

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def _format_figure_explanation(self, explanation: Optional[str]) -> str:
        """Format figure explanation for HTML."""
        if not explanation:
            return ""

        html_parts = ['<h3>🔍 Figure 해설</h3>', '<div class="figure-explanation">']
        html_parts.append(self._format_summary(explanation))
        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def generate_html(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: Optional[dict] = None
    ) -> str:
        """
        Generate HTML report.

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}

        Returns:
            HTML string
        """
        figure_explanations = figure_explanations or {}
        date_str = datetime.now().strftime("%Y년 %m월 %d일")

        # Generate TOC
        toc_items = []
        for i, pp in enumerate(processed_papers, 1):
            title_short = pp.paper.title[:50] + "..." if len(pp.paper.title) > 50 else pp.paper.title
            toc_items.append(f'<div class="toc-item"><a href="#paper-{i}">{i}. {title_short}</a></div>')

        # Generate paper sections
        paper_sections = []
        for i, pp in enumerate(processed_papers, 1):
            paper = pp.paper
            paper_id = paper.doi or paper.title

            # Get figure explanation
            fig_explanation = figure_explanations.get(paper_id, "")

            section = PAPER_SECTION_TEMPLATE.format(
                index=i,
                title=paper.title,
                journal=paper.journal,
                pub_date=paper.publication_date.strftime("%Y-%m-%d") if paper.publication_date else "N/A",
                url=paper.url,
                doi=paper.doi or "N/A",
                summary=self._format_summary(pp.summary_korean),
                translation=self._format_translation(pp.abstract_translation),
                figures_section=self._format_figures(pp.figures),
                figure_explanation_section=self._format_figure_explanation(fig_explanation)
            )
            paper_sections.append(section)

        # Generate full HTML
        html = HTML_TEMPLATE.format(
            date=date_str,
            paper_count=len(processed_papers),
            toc_items='\n'.join(toc_items),
            paper_sections='\n'.join(paper_sections)
        )

        return html

    def generate_pdf(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: Optional[dict] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate PDF report.

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}
            filename: Optional filename (default: paper_digest_YYYYMMDD.pdf)

        Returns:
            Path to generated PDF
        """
        from weasyprint import HTML

        # Generate HTML
        html_content = self.generate_html(processed_papers, figure_explanations)

        # Generate filename
        if not filename:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"paper_digest_{date_str}.pdf"

        output_path = self.output_dir / filename

        # Convert to PDF
        HTML(string=html_content).write_pdf(output_path)

        print(f"Generated PDF: {output_path}")
        return str(output_path)

    def generate_html_file(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: Optional[dict] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate HTML file (useful for preview).

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}
            filename: Optional filename

        Returns:
            Path to generated HTML
        """
        html_content = self.generate_html(processed_papers, figure_explanations)

        if not filename:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"paper_digest_{date_str}.html"

        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"Generated HTML: {output_path}")
        return str(output_path)
