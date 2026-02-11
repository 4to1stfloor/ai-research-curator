"""Main pipeline for automatic paper scraping."""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import load_config, resolve_path, AppConfig, EnvConfig
from .models import Paper, ProcessedPaper, ProcessingInfo
from .search.pubmed import PubMedSearcher
from .search.rss_feed import RSSFeedSearcher
from .search.biorxiv import BioRxivSearcher
from .storage.history import PaperHistoryManager
from .paper.deduplication import DeduplicationChecker
from .paper.downloader import PaperDownloader
from .paper.parser import PDFParser
from .paper.content_fetcher import PaperContentFetcher
from .ai.llm_client import LLMClient
from .ai.summarizer import PaperSummarizer, FigureExplanationGenerator
from .ai.translator import AbstractTranslator
from .output.pdf_report import PDFReportGenerator
from .output.obsidian import ObsidianExporter

console = Console()


class PaperDigestPipeline:
    """Main pipeline for paper digest generation."""

    def __init__(
        self,
        config: AppConfig,
        env_config: EnvConfig,
        base_dir: Optional[Path] = None
    ):
        """
        Initialize pipeline.

        Args:
            config: Application configuration
            env_config: Environment configuration (API keys)
            base_dir: Base directory for relative paths
        """
        self.config = config
        self.env_config = env_config
        self.base_dir = base_dir or Path.cwd()

        # Initialize components
        self._init_components()

    def _init_components(self):
        """Initialize all pipeline components."""
        # Storage
        history_path = resolve_path(self.config.storage.history_file, self.base_dir)
        self.history_manager = PaperHistoryManager(history_path)
        self.dedup_checker = DeduplicationChecker(self.history_manager)

        # Searchers
        self.pubmed_searcher = PubMedSearcher(email=self.env_config.pubmed_email)
        self.rss_searcher = RSSFeedSearcher()
        self.biorxiv_searcher = BioRxivSearcher()

        # Downloader & Parser
        papers_dir = resolve_path(self.config.storage.papers_dir, self.base_dir)
        self.papers_dir = papers_dir
        self.downloader = PaperDownloader(papers_dir, email=self.env_config.pubmed_email)
        self.pdf_parser = PDFParser(papers_dir / "figures")

        # Content Fetcher (for web-based content retrieval)
        self.content_fetcher = PaperContentFetcher(papers_dir / "figures")

        # Diagrams directory
        self.diagrams_dir = resolve_path(self.config.output.reports_path, self.base_dir).parent / "diagrams"
        self.diagrams_dir.mkdir(parents=True, exist_ok=True)

        # AI Components (initialized lazily)
        self._llm_client = None
        self._summarizer = None
        self._translator = None
        self._figure_explanation_gen = None

        # Output
        reports_path = resolve_path(self.config.output.reports_path, self.base_dir)
        self.pdf_generator = PDFReportGenerator(reports_path)

        if self.config.output.obsidian.enabled:
            obsidian_path = resolve_path(self.config.output.obsidian.vault_path, self.base_dir)
            self.obsidian_exporter = ObsidianExporter(obsidian_path)
        else:
            self.obsidian_exporter = None

    @staticmethod
    def _check_claude_cli() -> bool:
        """Check if Claude CLI is available."""
        import subprocess
        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _resolve_provider(self) -> str:
        """Resolve LLM provider. 'auto' detects available backends.

        Priority: Claude CLI → Anthropic API → Gemini API → OpenAI API → Ollama
        """
        provider = self.config.ai.llm_provider

        if provider != "auto":
            return provider

        # 1순위: Claude CLI (구독만으로 사용, API 키 불필요)
        if self._check_claude_cli():
            console.print("[green]Auto-detect: Claude CLI found → Claude 구독 사용[/green]")
            return "claude_cli"

        # 2순위: Anthropic API Key
        if self.env_config.anthropic_api_key:
            console.print("[green]Auto-detect: ANTHROPIC_API_KEY found → Claude API 사용[/green]")
            return "claude"

        # 3순위: Gemini API Key
        if self.env_config.google_api_key:
            console.print("[green]Auto-detect: GOOGLE_API_KEY found → Gemini 사용[/green]")
            return "gemini"

        # 4순위: OpenAI API Key
        if self.env_config.openai_api_key:
            console.print("[green]Auto-detect: OPENAI_API_KEY found → OpenAI 사용[/green]")
            return "openai"

        # 5순위: Ollama (로컬 LLM)
        console.print("[yellow]Auto-detect: API key 없음 → Ollama 사용[/yellow]")
        return "ollama"

    @property
    def llm_client(self) -> LLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            provider = self._resolve_provider()

            if provider == "claude_cli":
                self._llm_client = LLMClient.from_config(provider="claude_cli")
            elif provider == "claude":
                if not self.env_config.anthropic_api_key:
                    raise ValueError("ANTHROPIC_API_KEY required for Claude")
                self._llm_client = LLMClient.from_config(
                    provider="claude",
                    anthropic_key=self.env_config.anthropic_api_key,
                    claude_config=self.config.ai.claude.model_dump()
                )
            elif provider == "openai":
                if not self.env_config.openai_api_key:
                    raise ValueError("OPENAI_API_KEY required for OpenAI")
                self._llm_client = LLMClient.from_config(
                    provider="openai",
                    openai_key=self.env_config.openai_api_key,
                    openai_config=self.config.ai.openai.model_dump()
                )
            elif provider == "ollama":
                self._llm_client = LLMClient.from_config(
                    provider="ollama",
                    ollama_config=self.config.ai.ollama.model_dump()
                )
            elif provider == "gemini":
                if not self.env_config.google_api_key:
                    raise ValueError("GOOGLE_API_KEY required for Gemini")
                self._llm_client = LLMClient.from_config(
                    provider="gemini",
                    google_key=self.env_config.google_api_key,
                    gemini_config=self.config.ai.gemini.model_dump()
                )
            else:
                raise ValueError(f"Unknown LLM provider: {provider}")

        return self._llm_client

    @property
    def summarizer(self) -> PaperSummarizer:
        if self._summarizer is None:
            self._summarizer = PaperSummarizer(self.llm_client)
        return self._summarizer

    @property
    def translator(self) -> AbstractTranslator:
        if self._translator is None:
            self._translator = AbstractTranslator(self.llm_client)
        return self._translator

    @property
    def figure_explanation_generator(self) -> FigureExplanationGenerator:
        if self._figure_explanation_gen is None:
            self._figure_explanation_gen = FigureExplanationGenerator(self.llm_client)
        return self._figure_explanation_gen

    def search_papers(self, search_multiplier: int = 10, days_lookback_override: int = None) -> list[Paper]:
        """Search for papers from all configured sources.

        Args:
            search_multiplier: Multiply max_papers by this to get more candidates
            days_lookback_override: Override days_lookback setting
        """
        all_papers = []
        search_config = self.config.search
        days = days_lookback_override or search_config.days_lookback

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:

            # PubMed
            if "pubmed" in search_config.sources:
                task = progress.add_task("Searching PubMed...", total=None)
                papers = self.pubmed_searcher.search(
                    keywords=search_config.keywords,
                    journals=search_config.journals,
                    max_papers=search_config.max_papers * search_multiplier,
                    days_lookback=days
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

            # RSS
            if "rss" in search_config.sources:
                task = progress.add_task("Searching RSS feeds...", total=None)
                papers = self.rss_searcher.search(
                    keywords=search_config.keywords,
                    journals=search_config.journals,
                    max_papers=search_config.max_papers * search_multiplier,
                    days_lookback=days
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

            # bioRxiv
            if "biorxiv" in search_config.sources:
                task = progress.add_task("Searching bioRxiv...", total=None)
                papers = self.biorxiv_searcher.search(
                    keywords=search_config.keywords,
                    max_papers=search_config.max_papers * search_multiplier,
                    days_lookback=days
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

        console.print(f"[green]Found {len(all_papers)} papers total[/green]")
        return all_papers

    def filter_papers(self, papers: list[Paper]) -> list[Paper]:
        """Filter out duplicates, non-research articles, and limit to max_papers."""
        # Remove duplicates
        unique_papers = self.dedup_checker.filter_duplicates(papers)
        console.print(f"[yellow]After deduplication: {len(unique_papers)} papers[/yellow]")

        # Filter out non-research articles (Perspective, Review, Editorial, etc.)
        non_research_types = [
            "Review", "Editorial", "Comment", "Letter", "News",
            "Published Erratum", "Retracted Publication", "Biography",
            "Historical Article", "Interview", "Lecture", "Guideline",
            "Perspective", "Commentary", "Opinion", "Correspondence",
            "Correction", "Retraction", "Primer", "Viewpoint"
        ]
        research_papers = []
        filtered_count = 0
        for p in unique_papers:
            is_research = True
            if p.article_type:
                for nrt in non_research_types:
                    if nrt.lower() in p.article_type.lower():
                        is_research = False
                        filtered_count += 1
                        break
            if is_research:
                research_papers.append(p)

        if filtered_count > 0:
            console.print(f"[yellow]Filtered out {filtered_count} non-research articles (Review, Perspective, etc.)[/yellow]")
        unique_papers = research_papers

        # Filter open access only if enabled
        if self.config.search.open_access_only:
            open_access_papers = [p for p in unique_papers if p.is_open_access or p.pdf_url]
            console.print(f"[yellow]Open access only: {len(open_access_papers)} papers[/yellow]")
            unique_papers = open_access_papers

        # Limit to max_papers
        max_papers = self.config.search.max_papers
        if len(unique_papers) > max_papers:
            unique_papers = unique_papers[:max_papers]
            console.print(f"[yellow]Limited to {max_papers} papers[/yellow]")

        return unique_papers

    def download_papers(self, papers: list[Paper]) -> list[Paper]:
        """Download PDFs for open access papers."""
        console.print("[cyan]Downloading papers...[/cyan]")

        for paper in papers:
            if paper.is_open_access or paper.pdf_url:
                self.downloader.download(paper)

        pdf_count = len([p for p in papers if p.local_pdf_path])
        console.print(f"[green]Downloaded {pdf_count} PDFs[/green]")

        return papers

    def process_papers(self, papers: list[Paper]) -> tuple[list[ProcessedPaper], dict, dict]:
        """Process papers with AI (summarize, translate).

        Content is fetched in this priority:
        1. Local PDF (if downloaded)
        2. Web-based content fetcher (PMC, bioRxiv, DOI)
        3. Abstract only (fallback)

        Returns:
            Tuple of (processed_papers, body_texts_dict, diagrams_dict)
        """
        processed = []
        body_texts = {}
        diagrams = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:

            for i, paper in enumerate(papers, 1):
                task = progress.add_task(
                    f"Processing {i}/{len(papers)}: {paper.title[:40]}...",
                    total=None
                )

                # Initialize processing info for this paper
                proc_info = ProcessingInfo()

                # Fetch abstract from DOI if not available or too short (e.g., RSS source)
                if paper.doi and (not paper.abstract or len(paper.abstract) < 500):
                    fetched_abstract = self.content_fetcher.fetch_abstract_from_doi(paper.doi)
                    if fetched_abstract and len(fetched_abstract) > len(paper.abstract or ""):
                        paper.abstract = fetched_abstract
                        proc_info.add_note("DOI에서 abstract 추가 fetch")

                try:
                    body_text = ""
                    figures = []
                    figure_legends = []

                    # Method 1: Try web-based figure extraction first (more accurate)
                    console.print(f"[cyan]Fetching figures from web: {paper.title[:40]}...[/cyan]")
                    content = self.content_fetcher.fetch_content(paper)

                    if content.get("text"):
                        body_text = content.get("text", "")
                        proc_info.full_text_available = True
                        proc_info.abstract_only = False

                    figures = content.get("figures", [])
                    if figures:
                        proc_info.figures_extracted = True
                        proc_info.figures_source = content.get("source", "web")
                        proc_info.figures_count = len(figures)
                        proc_info.add_note(f"{proc_info.figures_source}에서 {len(figures)}개 Figure 추출")

                    if content.get("figure_legends"):
                        figure_legends_text = content.get("figure_legends", "")
                        for legend in figure_legends_text.split("\n\n"):
                            if legend.strip():
                                match = re.match(r'Figure\s+(\d+[A-Za-z]?):\s*(.+)', legend, re.DOTALL)
                                if match:
                                    figure_legends.append({
                                        "figure_num": match.group(1),
                                        "legend": match.group(2).strip()
                                    })

                    # Method 2: Parse local PDF for text (not figures - web is more accurate)
                    if paper.local_pdf_path:
                        proc_info.pdf_downloaded = True
                        proc_info.add_note("PDF 다운로드 완료")

                        parsed = self.pdf_parser.parse_paper(paper, extract_figures=False)
                        if not body_text and parsed.get("text"):
                            body_text = parsed.get("text", "")
                            proc_info.full_text_available = True
                            proc_info.abstract_only = False
                            proc_info.add_note("PDF에서 본문 추출 완료")

                        if parsed.get("figure_legends"):
                            figure_legends.extend(parsed.get("figure_legends", []))
                    else:
                        proc_info.pdf_downloaded = False
                        proc_info.pdf_download_error = "PDF를 찾을 수 없음"

                    # Set final status if no figures extracted
                    if not figures:
                        proc_info.figures_extracted = False
                        if not proc_info.figures_error:
                            proc_info.figures_error = "Figure를 추출할 수 있는 소스가 없음"
                        proc_info.add_note("Figure 없음 - Abstract 기반 분석만 진행")

                    # Set abstract_only status if no body text
                    if not body_text:
                        proc_info.full_text_available = False
                        proc_info.abstract_only = True
                        proc_info.add_note("본문 없음 - Abstract만 분석")

                    # Store body text for figure explanation
                    paper_id = paper.doi or paper.title
                    body_texts[paper_id] = body_text

                    # Summarize (will use abstract-only prompt if no body_text)
                    summary = self.summarizer.summarize(paper, body_text)

                    # Translate abstract
                    translation = []
                    if self.config.ai.translate_abstract and paper.abstract:
                        translation = self.translator.translate(paper.abstract)

                    # Generate diagram if enabled
                    if self.config.ai.generate_summary_image:
                        diagram = self._generate_diagram(paper, summary)
                        if diagram:
                            diagrams[paper_id] = diagram

                    processed_paper = ProcessedPaper(
                        paper=paper,
                        summary_korean=summary,
                        abstract_translation=translation,
                        figures=figures,
                        llm_provider=self.config.ai.llm_provider,
                        processing_info=proc_info
                    )
                    processed.append(processed_paper)

                    # Log processing status
                    status_msg = proc_info.get_status_summary()
                    console.print(f"[green]Processed: {paper.title[:40]}...[/green]")
                    console.print(f"  [dim]{status_msg}[/dim]")

                except Exception as e:
                    console.print(f"[red]Error processing {paper.title[:40]}: {e}[/red]")
                    import traceback
                    traceback.print_exc()

                    # Create error processing info
                    error_info = ProcessingInfo()
                    error_info.add_note(f"처리 오류: {str(e)}")

                    # Add with minimal processing
                    processed.append(ProcessedPaper(
                        paper=paper,
                        summary_korean=f"(처리 오류 발생: {str(e)})",
                        abstract_translation=[],
                        figures=[],
                        processing_info=error_info
                    ))

                progress.update(task, completed=True)

        return processed, body_texts, diagrams

    def _generate_diagram(self, paper: Paper, summary: str) -> Optional[str]:
        """Generate a Mermaid diagram for the paper."""
        try:
            prompt = f"""Based on this paper summary, create a simple Mermaid flowchart diagram.

Paper Title: {paper.title}

Summary:
{summary}

RULES:
1. Start with 'flowchart TD' (top-down) or 'flowchart LR' (left-right)
2. Use simple node IDs like A, B, C, D, E
3. Node format: A[노드 텍스트]
4. Arrow format: A --> B (simple arrow) or A -->|라벨| B (with label)
5. Keep it simple: 4-6 nodes maximum
6. Use Korean for labels
7. Do NOT use special characters like &, --, or subgraphs
8. Do NOT include ```mermaid or ``` markers

Example:
flowchart TD
    A[입력 데이터] --> B[전처리]
    B --> C[분석]
    C --> D[결과]
"""
            diagram = self.llm_client.generate(prompt)

            # Clean up: extract Mermaid code from response
            diagram = diagram.strip()

            # If response contains code block markers, extract content between them
            code_block_match = re.search(r'```(?:mermaid)?\s*((?:flowchart|graph)[\s\S]*?)```', diagram, re.IGNORECASE)
            if code_block_match:
                diagram = code_block_match.group(1).strip()
            else:
                # No code block markers, try to find flowchart/graph directly
                flowchart_match = re.search(r'((?:flowchart|graph)\s+(?:TD|LR|TB|RL|BT)[\s\S]*?)(?:\n\n[A-Za-z]|$)', diagram, re.IGNORECASE)
                if flowchart_match:
                    diagram = flowchart_match.group(1).strip()
                else:
                    # Fallback: remove markdown markers at start/end
                    diagram = re.sub(r'^```(?:mermaid)?\s*', '', diagram)
                    diagram = re.sub(r'\s*```$', '', diagram)
                    diagram = diagram.strip()

            # Fix common Mermaid syntax issues
            # Fix: "A -- label --> B" to "A -->|label| B"
            diagram = re.sub(r'(\w+)\s*--\s*([^->\n]+)\s*-->\s*(\w+)', r'\1 -->|\2| \3', diagram)
            # Fix: "A & B --> C" to separate lines
            diagram = re.sub(r'(\w+)\s*&\s*(\w+)\s*-->\s*(\w+)', r'\1 --> \3\n    \2 --> \3', diagram)
            # Remove any remaining problematic characters
            diagram = diagram.replace('&', '')

            # Fix: Quote node text with spaces or special chars for Korean support
            def quote_node_text(match):
                prefix = match.group(1)  # Node ID and bracket type
                text = match.group(2)    # Node text
                suffix = match.group(3)  # Closing bracket
                # If text has spaces or special chars and not already quoted
                if ' ' in text and not (text.startswith('"') and text.endswith('"')):
                    text = f'"{text}"'
                return f'{prefix}{text}{suffix}'

            # Match node patterns: A[text], A{text}, A(text), A((text))
            diagram = re.sub(r'(\w+\[)([^\]]+)(\])', quote_node_text, diagram)
            diagram = re.sub(r'(\w+\{)([^\}]+)(\})', quote_node_text, diagram)
            diagram = re.sub(r'(\w+\()([^\)]+)(\))', quote_node_text, diagram)

            # Validate it's a mermaid diagram
            if 'flowchart' in diagram.lower() or 'graph' in diagram.lower():
                # Save to file
                paper_id = self._sanitize_filename(paper.title[:50])
                diagram_path = self.diagrams_dir / f"{paper_id}.md"
                with open(diagram_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Diagram: {paper.title}\n\n```mermaid\n{diagram}\n```")

                console.print(f"[green]Generated diagram for: {paper.title[:40]}...[/green]")
                return diagram

        except Exception as e:
            console.print(f"[yellow]Diagram generation error: {e}[/yellow]")

        return None

    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title."""
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:50]

    def generate_figure_explanations(
        self,
        processed_papers: list[ProcessedPaper],
        body_texts: dict
    ) -> dict:
        """Generate figure explanations for papers."""
        explanations = {}

        if not self.config.ai.generate_summary_image:
            return explanations

        console.print("[cyan]Generating figure explanations...[/cyan]")

        for pp in processed_papers:
            paper_id = pp.paper.doi or pp.paper.title
            try:
                # Check if paper has figures
                has_figures = bool(pp.figures)

                # Extract figure legends from body text
                body_text = body_texts.get(paper_id, "")
                legends = []
                if body_text:
                    legends = self.figure_explanation_generator.extract_figure_legends(body_text)

                # Skip if no figures and no legends
                if not has_figures and not legends:
                    continue

                # Combine legends for explanation
                legend_text = "\n".join([
                    f"Figure {l['figure_num']}: {l['legend']}"
                    for l in legends
                ]) if legends else ""

                # Also include captions from figures
                for fig in pp.figures:
                    if isinstance(fig, dict) and fig.get('caption'):
                        legend_text += f"\nFigure {fig.get('figure_num', '?')}: {fig['caption']}"

                # If we have figures but no legend text, create placeholder info
                if not legend_text.strip() and has_figures:
                    fig_count = len(pp.figures)
                    legend_text = f"(논문에서 추출한 {fig_count}개의 Figure가 있습니다. Figure legend 텍스트는 추출되지 않았습니다. 논문 요약을 기반으로 Figure의 내용을 추측하여 설명해주세요.)"
                elif not legend_text.strip():
                    continue

                # Generate explanation
                explanation = self.figure_explanation_generator.generate_explanation(
                    pp.paper,
                    pp.summary_korean,
                    legend_text
                )
                explanations[paper_id] = explanation
                console.print(f"[green]Generated figure explanation for: {pp.paper.title[:40]}...[/green]")

            except Exception as e:
                console.print(f"[yellow]Figure explanation error: {e}[/yellow]")

        return explanations

    def generate_output(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: dict,
        diagrams: dict
    ) -> dict:
        """Generate output files (PDF, HTML, Obsidian)."""
        result = {}

        # Generate HTML (always, as fallback for PDF)
        console.print("[cyan]Generating HTML report...[/cyan]")
        try:
            html_path = self.pdf_generator.generate_html_file(
                processed_papers, figure_explanations, diagrams
            )
            result["html"] = html_path
            console.print(f"[green]HTML: {html_path}[/green]")
        except Exception as e:
            console.print(f"[red]HTML error: {e}[/red]")

        # Generate PDF
        if self.config.output.pdf_report:
            console.print("[cyan]Generating PDF report...[/cyan]")
            try:
                pdf_path = self.pdf_generator.generate_pdf(
                    processed_papers, figure_explanations, diagrams
                )
                result["pdf"] = pdf_path
                console.print(f"[green]PDF: {pdf_path}[/green]")
            except Exception as e:
                console.print(f"[yellow]PDF generation failed (using HTML): {e}[/yellow]")

        # Generate Obsidian notes
        if self.obsidian_exporter:
            console.print("[cyan]Exporting to Obsidian...[/cyan]")
            try:
                obsidian_result = self.obsidian_exporter.export_all(
                    processed_papers,
                    figure_explanations,
                    create_digest=True
                )
                result["obsidian"] = obsidian_result
                console.print(f"[green]Obsidian: {len(obsidian_result['paper_paths'])} notes[/green]")
            except Exception as e:
                console.print(f"[red]Obsidian error: {e}[/red]")

        return result

    def save_to_history(self, papers: list[Paper]):
        """Save processed papers to history."""
        self.dedup_checker.save_to_history(papers)
        console.print(f"[green]Saved {len(papers)} papers to history[/green]")

    def run(self) -> dict:
        """Run the complete pipeline."""
        console.print("[bold blue]Paper Digest Pipeline[/bold blue]")
        console.print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        console.print("=" * 50)

        max_papers = self.config.search.max_papers

        # 1. Search
        all_papers = self.search_papers()
        if not all_papers:
            console.print("[yellow]No papers found![/yellow]")
            return {"papers": 0}

        # 2. Filter
        papers = self.filter_papers(all_papers)
        if not papers:
            console.print("[yellow]No new papers after filtering![/yellow]")
            return {"papers": 0}

        if len(papers) < max_papers:
            console.print(f"[yellow]Found {len(papers)} papers (requested {max_papers}). Consider adding more keywords or journals in config.[/yellow]")

        # Display found papers
        table = Table(title="Found Papers")
        table.add_column("No", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Journal", style="green")
        for i, p in enumerate(papers, 1):
            table.add_row(str(i), p.title[:60] + "...", p.journal)
        console.print(table)

        # 3. Download
        papers = self.download_papers(papers)

        # 4. Process with AI
        processed, body_texts, diagrams = self.process_papers(papers)

        # 5. Generate figure explanations
        figure_explanations = self.generate_figure_explanations(processed, body_texts)

        # 6. Generate output
        output = self.generate_output(processed, figure_explanations, diagrams)

        # 7. Save to history
        self.save_to_history(papers)

        console.print("=" * 50)
        console.print("[bold green]Pipeline completed![/bold green]")

        return {
            "papers": len(papers),
            "output": output
        }


# CLI
@click.command()
@click.option(
    '--config', '-c',
    default='config/config.yaml',
    help='Configuration file path'
)
@click.option(
    '--max-papers', '-n',
    type=int,
    default=None,
    help='Override max papers to process'
)
@click.option(
    '--days', '-d',
    type=int,
    default=None,
    help='Override days to look back'
)
@click.option(
    '--no-pdf',
    is_flag=True,
    help='Skip PDF report generation'
)
@click.option(
    '--no-obsidian',
    is_flag=True,
    help='Skip Obsidian export'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Search only, do not process'
)
@click.option(
    '--open-access-only',
    is_flag=True,
    help='Only process open access papers (with PDFs)'
)
def main(config, max_papers, days, no_pdf, no_obsidian, dry_run, open_access_only):
    """Automatic Paper Scraping AI Agent."""
    try:
        # Load configuration
        config_path = Path(config)
        if not config_path.exists():
            console.print(f"[red]Config file not found: {config}[/red]")
            console.print("Creating default config...")
            from .config import AppConfig
            default_config = AppConfig()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config.to_yaml(config_path)

        app_config, env_config = load_config(config_path)

        # Override settings
        if max_papers:
            app_config.search.max_papers = max_papers
        if days:
            app_config.search.days_lookback = days
        if no_pdf:
            app_config.output.pdf_report = False
        if no_obsidian:
            app_config.output.obsidian.enabled = False
        if open_access_only:
            app_config.search.open_access_only = True

        # Check API keys (skip for dry-run, ollama)
        if not dry_run and app_config.ai.llm_provider not in ("ollama",):
            provider = app_config.ai.llm_provider
            if provider == "claude" and not env_config.anthropic_api_key:
                console.print("[red]Error: ANTHROPIC_API_KEY required for Claude![/red]")
                sys.exit(1)
            elif provider == "openai" and not env_config.openai_api_key:
                console.print("[red]Error: OPENAI_API_KEY required for OpenAI![/red]")
                sys.exit(1)
            elif provider == "gemini" and not env_config.google_api_key:
                console.print("[red]Error: GOOGLE_API_KEY required for Gemini![/red]")
                sys.exit(1)

        # Initialize and run pipeline
        base_dir = config_path.parent.parent  # Assume config is in config/
        pipeline = PaperDigestPipeline(app_config, env_config, base_dir)

        if dry_run:
            papers = pipeline.search_papers()
            papers = pipeline.filter_papers(papers)
            console.print(f"\n[yellow]Dry run: Would process {len(papers)} papers[/yellow]")
            return

        result = pipeline.run()
        console.print(f"\n[bold]Result: Processed {result['papers']} papers[/bold]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
