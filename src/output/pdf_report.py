"""HTML/PDF report generator with improved design and Mermaid support."""

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Paper, ProcessedPaper


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Digest - {date}</title>

    <!-- Mermaid.js for diagrams -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>

    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <style>
        :root {{
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --secondary: #64748b;
            --accent: #0ea5e9;
            --success: #22c55e;
            --warning: #f59e0b;
            --bg-light: #f8fafc;
            --bg-card: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border: #e2e8f0;
            --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Noto Sans KR', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.7;
            color: var(--text-primary);
            background: var(--bg-light);
            padding: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 3rem;
            border-radius: 1rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow-lg);
        }}

        .header h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .header .subtitle {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header .stats {{
            display: flex;
            gap: 2rem;
            margin-top: 1.5rem;
        }}

        .header .stat {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .header .stat-value {{
            font-size: 1.5rem;
            font-weight: 600;
        }}

        /* Table of Contents */
        .toc {{
            background: var(--bg-card);
            padding: 1.5rem 2rem;
            border-radius: 0.75rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow);
        }}

        .toc-title {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .toc-list {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 0.75rem;
        }}

        .toc-item {{
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
        }}

        .toc-num {{
            background: var(--primary);
            color: white;
            width: 1.75rem;
            height: 1.75rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.875rem;
            font-weight: 600;
            flex-shrink: 0;
        }}

        .toc-item a {{
            color: var(--text-primary);
            text-decoration: none;
            font-size: 0.95rem;
            line-height: 1.4;
            transition: color 0.2s;
        }}

        .toc-item a:hover {{
            color: var(--primary);
        }}

        /* Paper Card */
        .paper {{
            background: var(--bg-card);
            border-radius: 1rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow);
            overflow: hidden;
        }}

        .paper-header {{
            padding: 2rem;
            border-bottom: 1px solid var(--border);
        }}

        .paper-num {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--primary);
            color: white;
            width: 2.5rem;
            height: 2.5rem;
            border-radius: 50%;
            font-weight: 600;
            margin-bottom: 1rem;
        }}

        .paper-title {{
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.4;
            margin-bottom: 1rem;
        }}

        .paper-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
        }}

        .meta-item {{
            display: flex;
            align-items: center;
            gap: 0.375rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .meta-item a {{
            color: var(--primary);
            text-decoration: none;
        }}

        .meta-item a:hover {{
            text-decoration: underline;
        }}

        .paper-body {{
            padding: 2rem;
        }}

        /* Sections */
        .section {{
            margin-bottom: 2rem;
        }}

        .section:last-child {{
            margin-bottom: 0;
        }}

        .section-title {{
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border);
        }}

        .section-content {{
            color: var(--text-secondary);
        }}

        .section-content h4 {{
            color: var(--text-primary);
            font-size: 1rem;
            font-weight: 600;
            margin: 1.25rem 0 0.5rem 0;
        }}

        .section-content h5 {{
            color: var(--accent);
            font-size: 0.95rem;
            font-weight: 600;
            margin: 1.5rem 0 0.75rem 0;
            padding-bottom: 0.25rem;
            border-bottom: 1px solid var(--border);
        }}

        .section-content ul, .section-content ol {{
            margin: 0.5rem 0;
            padding-left: 1.5rem;
        }}

        .section-content li {{
            margin: 0.375rem 0;
        }}

        .section-content p {{
            margin: 0.5rem 0;
        }}

        /* Translation */
        .translation-pair {{
            margin-bottom: 1.25rem;
            padding-bottom: 1.25rem;
            border-bottom: 1px dashed var(--border);
        }}

        .translation-pair:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}

        .translation-num {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--bg-light);
            color: var(--text-secondary);
            width: 1.5rem;
            height: 1.5rem;
            border-radius: 50%;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 0.5rem;
        }}

        .translation-en {{
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }}

        .translation-ko {{
            color: var(--text-secondary);
            padding-left: 1rem;
            border-left: 3px solid var(--primary);
            background: var(--bg-light);
            padding: 0.75rem 1rem;
            border-radius: 0 0.5rem 0.5rem 0;
        }}

        /* Figures */
        .figures-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-top: 1rem;
        }}

        .figure-card {{
            background: var(--bg-light);
            border-radius: 0.75rem;
            overflow: hidden;
            border: 1px solid var(--border);
        }}

        .figure-img {{
            width: 100%;
            height: auto;
            display: block;
        }}

        .figure-caption {{
            padding: 1rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .figure-num {{
            font-weight: 600;
            color: var(--primary);
        }}

        /* Figure Explanation */
        .figure-explanation {{
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-radius: 0.75rem;
            padding: 1.5rem;
            border-left: 4px solid var(--accent);
        }}

        .figure-explanation h4 {{
            color: var(--accent);
        }}

        /* Mermaid Diagram */
        .mermaid-container {{
            background: var(--bg-light);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-top: 1rem;
            overflow-x: auto;
        }}

        .mermaid {{
            text-align: center;
        }}

        /* Footer */
        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.875rem;
        }}

        .footer a {{
            color: var(--primary);
            text-decoration: none;
        }}

        /* Print styles */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}

            .container {{
                max-width: 100%;
            }}

            .paper {{
                break-inside: avoid;
                box-shadow: none;
                border: 1px solid var(--border);
            }}

            .header {{
                background: var(--primary);
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}

            .header {{
                padding: 2rem;
            }}

            .header h1 {{
                font-size: 1.75rem;
            }}

            .header .stats {{
                flex-direction: column;
                gap: 0.75rem;
            }}

            .toc-list {{
                grid-template-columns: 1fr;
            }}

            .paper-header, .paper-body {{
                padding: 1.5rem;
            }}

            .paper-title {{
                font-size: 1.25rem;
            }}

            .figures-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>Paper Digest</h1>
            <p class="subtitle">{date}</p>
            <div class="stats">
                <div class="stat">
                    <span class="stat-value">{paper_count}</span>
                    <span>Papers</span>
                </div>
            </div>
        </header>

        <nav class="toc">
            <h2 class="toc-title">Table of Contents</h2>
            <div class="toc-list">
                {toc_items}
            </div>
        </nav>

        <main>
            {paper_sections}
        </main>

        <footer class="footer">
            <p>Generated by <strong>Paper Digest AI</strong> | {date}</p>
        </footer>
    </div>
</body>
</html>
"""

PAPER_SECTION_TEMPLATE = """
<article class="paper" id="paper-{index}">
    <header class="paper-header">
        <div class="paper-num">{index}</div>
        <h2 class="paper-title">{title}</h2>
        <div class="paper-meta">
            <span class="meta-item">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828zm7.5-.141c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492V2.687zM8 1.783C7.015.936 5.587.81 4.287.94c-1.514.153-3.042.672-3.994 1.105A.5.5 0 0 0 0 2.5v11a.5.5 0 0 0 .707.455c.882-.4 2.303-.881 3.68-1.02 1.409-.142 2.59.087 3.223.877a.5.5 0 0 0 .78 0c.633-.79 1.814-1.019 3.222-.877 1.378.139 2.8.62 3.681 1.02A.5.5 0 0 0 16 13.5v-11a.5.5 0 0 0-.293-.455c-.952-.433-2.48-.952-3.994-1.105C10.413.809 8.985.936 8 1.783z"/>
                </svg>
                {journal}
            </span>
            <span class="meta-item">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M11 6.5a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1zm-3 0a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1zm-5 3a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1zm3 0a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1z"/>
                    <path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/>
                </svg>
                {pub_date}
            </span>
            <span class="meta-item">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/>
                    <path fill-rule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/>
                </svg>
                <a href="{url}" target="_blank">{doi}</a>
            </span>
        </div>
    </header>

    <div class="paper-body">
        <section class="section">
            <h3 class="section-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M5 4a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm-.5 2.5A.5.5 0 0 1 5 6h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zM5 8a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm0 2a.5.5 0 0 0 0 1h3a.5.5 0 0 0 0-1H5z"/>
                    <path d="M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2zm10-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1z"/>
                </svg>
                Summary
            </h3>
            <div class="section-content">
                {summary}
            </div>
        </section>

        <section class="section">
            <h3 class="section-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2zm2-1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H2z"/>
                    <path d="M2 4.5a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5zm0 3a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5zm0 3a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5z"/>
                </svg>
                Abstract Translation
            </h3>
            <div class="section-content">
                {translation}
            </div>
        </section>

        {figures_section}

        {figure_explanation_section}

        {diagram_section}
    </div>
</article>
"""


class PDFReportGenerator:
    """Generate PDF/HTML reports from processed papers."""

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
        list_type = None

        for line in lines:
            line = line.strip()

            # Convert inline **bold** to <strong>
            line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line)

            # Convert inline *italic* to <em>
            line = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', line)

            if not line:
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                    list_type = None
                continue
            elif line.startswith('#### '):
                # Convert #### to h5 for figure titles
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                html_lines.append(f'<h5>{line[5:]}</h5>')
            elif line.startswith('### '):
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                html_lines.append(f'<h4>{line[4:]}</h4>')
            elif line.startswith('## '):
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                html_lines.append(f'<h3>{line[3:]}</h3>')
            elif line.startswith('# '):
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                html_lines.append(f'<h3>{line[2:]}</h3>')
            elif line.startswith('- '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        html_lines.append('</ol>')
                    html_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                html_lines.append(f'<li>{line[2:]}</li>')
            elif re.match(r'^\d+\.', line):
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_lines.append('</ul>')
                    html_lines.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                content = re.sub(r'^\d+\.\s*', '', line)
                html_lines.append(f'<li>{content}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                    in_list = False
                    list_type = None
                html_lines.append(f'<p>{line}</p>')

        if in_list:
            html_lines.append('</ul>' if list_type == 'ul' else '</ol>')

        return '\n'.join(html_lines)

    def _format_translation(self, translations: list[dict]) -> str:
        """Format translation pairs for HTML."""
        html_parts = []

        for i, pair in enumerate(translations, 1):
            html_parts.append(f'''
            <div class="translation-pair">
                <p class="translation-en"><span class="translation-num">{i}</span>{pair.get('en', '')}</p>
                <p class="translation-ko">{pair.get('ko', '')}</p>
            </div>
            ''')

        return '\n'.join(html_parts) if html_parts else '<p class="text-muted">No translation available</p>'

    def _format_figures(self, figures: list) -> str:
        """Format figures for HTML.

        Args:
            figures: List of figure dicts with 'path', 'figure_num', 'caption'
        """
        if not figures:
            return ""

        html_parts = ['''
        <section class="section">
            <h3 class="section-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
                Figures
            </h3>
            <div class="figures-grid">
        ''']

        for fig_item in figures[:8]:  # Limit to 8 figures
            try:
                # Handle both string paths and dict format
                if isinstance(fig_item, dict):
                    fig_path = fig_item.get('path', '')
                    fig_num = fig_item.get('figure_num', '?')
                    caption = fig_item.get('caption', '')
                else:
                    fig_path = fig_item
                    fig_num = '?'
                    caption = ''

                if not fig_path or not Path(fig_path).exists():
                    continue

                # Embed image as base64
                with open(fig_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()

                ext = Path(fig_path).suffix.lower()
                mime = 'image/png' if ext == '.png' else 'image/jpeg' if ext in ['.jpg', '.jpeg'] else 'image/gif'

                caption_html = f'<p>{caption[:200]}...</p>' if len(caption) > 200 else f'<p>{caption}</p>' if caption else ''

                html_parts.append(f'''
                <div class="figure-card">
                    <img src="data:{mime};base64,{img_data}" alt="Figure {fig_num}" class="figure-img">
                    <div class="figure-caption">
                        <span class="figure-num">Figure {fig_num}</span>
                        {caption_html}
                    </div>
                </div>
                ''')
            except Exception as e:
                print(f"Error embedding figure {fig_item}: {e}")

        html_parts.append('</div></section>')

        # Only return if we actually have figures
        if len(html_parts) > 2:  # More than just the opening/closing tags
            return '\n'.join(html_parts)
        return ""

    def _format_figure_explanation(self, explanation: Optional[str]) -> str:
        """Format figure explanation for HTML."""
        if not explanation:
            return ""

        html_parts = ['''
        <section class="section">
            <h3 class="section-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
                    <path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533L8.93 6.588zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                </svg>
                Figure Analysis
            </h3>
            <div class="figure-explanation">
        ''']
        html_parts.append(self._format_summary(explanation))
        html_parts.append('</div></section>')
        return '\n'.join(html_parts)

    def _format_diagram(self, diagram_content: Optional[str]) -> str:
        """Format Mermaid diagram for HTML."""
        if not diagram_content:
            return ""

        # Extract mermaid code from markdown if present
        import re
        mermaid_match = re.search(r'```mermaid\s*([\s\S]*?)\s*```', diagram_content)
        if mermaid_match:
            mermaid_code = mermaid_match.group(1).strip()
        else:
            mermaid_code = diagram_content.strip()

        return f'''
        <section class="section">
            <h3 class="section-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M6 3.5A1.5 1.5 0 0 1 7.5 2h1A1.5 1.5 0 0 1 10 3.5v1A1.5 1.5 0 0 1 8.5 6v1H14a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-1 0V8h-5v.5a.5.5 0 0 1-1 0V8h-5v.5a.5.5 0 0 1-1 0v-1A.5.5 0 0 1 2 7h5.5V6A1.5 1.5 0 0 1 6 4.5v-1zM8.5 5a.5.5 0 0 0 .5-.5v-1a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1zM0 11.5A1.5 1.5 0 0 1 1.5 10h1A1.5 1.5 0 0 1 4 11.5v1A1.5 1.5 0 0 1 2.5 14h-1A1.5 1.5 0 0 1 0 12.5v-1zm1.5-.5a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1a.5.5 0 0 0-.5-.5h-1zm4.5.5A1.5 1.5 0 0 1 7.5 10h1a1.5 1.5 0 0 1 1.5 1.5v1A1.5 1.5 0 0 1 8.5 14h-1A1.5 1.5 0 0 1 6 12.5v-1zm1.5-.5a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1a.5.5 0 0 0-.5-.5h-1zm4.5.5a1.5 1.5 0 0 1 1.5-1.5h1a1.5 1.5 0 0 1 1.5 1.5v1a1.5 1.5 0 0 1-1.5 1.5h-1a1.5 1.5 0 0 1-1.5-1.5v-1zm1.5-.5a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1a.5.5 0 0 0-.5-.5h-1z"/>
                </svg>
                Workflow Diagram
            </h3>
            <div class="mermaid-container">
                <pre class="mermaid">
{mermaid_code}
                </pre>
            </div>
        </section>
        '''

    def generate_html(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: Optional[dict] = None,
        diagrams: Optional[dict] = None
    ) -> str:
        """
        Generate HTML report.

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}
            diagrams: Optional dict of {paper_id: mermaid_diagram}

        Returns:
            HTML string
        """
        figure_explanations = figure_explanations or {}
        diagrams = diagrams or {}
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Generate TOC
        toc_items = []
        for i, pp in enumerate(processed_papers, 1):
            title_short = pp.paper.title[:60] + "..." if len(pp.paper.title) > 60 else pp.paper.title
            toc_items.append(f'''
            <div class="toc-item">
                <span class="toc-num">{i}</span>
                <a href="#paper-{i}">{title_short}</a>
            </div>
            ''')

        # Generate paper sections
        paper_sections = []
        for i, pp in enumerate(processed_papers, 1):
            paper = pp.paper
            paper_id = paper.doi or paper.title

            # Get figure explanation and diagram
            fig_explanation = figure_explanations.get(paper_id, "")
            diagram = diagrams.get(paper_id, "")

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
                figure_explanation_section=self._format_figure_explanation(fig_explanation),
                diagram_section=self._format_diagram(diagram)
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
        diagrams: Optional[dict] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate PDF report.

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}
            diagrams: Optional dict of {paper_id: mermaid_diagram}
            filename: Optional filename (default: paper_digest_YYYYMMDD.pdf)

        Returns:
            Path to generated PDF
        """
        from weasyprint import HTML

        # Generate HTML
        html_content = self.generate_html(processed_papers, figure_explanations, diagrams)

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
        diagrams: Optional[dict] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate HTML file.

        Args:
            processed_papers: List of processed papers
            figure_explanations: Optional dict of {paper_id: figure_explanation}
            diagrams: Optional dict of {paper_id: mermaid_diagram}
            filename: Optional filename

        Returns:
            Path to generated HTML
        """
        html_content = self.generate_html(processed_papers, figure_explanations, diagrams)

        if not filename:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"paper_digest_{date_str}.html"

        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"Generated HTML: {output_path}")
        return str(output_path)
