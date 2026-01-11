"""Main pipeline for automatic paper scraping."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import load_config, resolve_path, AppConfig, EnvConfig
from .models import Paper, ProcessedPaper
from .search.pubmed import PubMedSearcher
from .search.rss_feed import RSSFeedSearcher
from .search.biorxiv import BioRxivSearcher
from .storage.history import PaperHistoryManager
from .paper.deduplication import DeduplicationChecker
from .paper.downloader import PaperDownloader
from .paper.parser import PDFParser
from .paper.content_fetcher import JinaContentFetcher
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
        self.downloader = PaperDownloader(papers_dir, email=self.env_config.pubmed_email)
        self.pdf_parser = PDFParser(papers_dir / "figures")

        # Jina Content Fetcher (for web-based content retrieval)
        self.content_fetcher = JinaContentFetcher(papers_dir / "figures")

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

    @property
    def llm_client(self) -> LLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            provider = self.config.ai.llm_provider

            if provider == "claude":
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

    def search_papers(self) -> list[Paper]:
        """Search for papers from all configured sources."""
        all_papers = []
        search_config = self.config.search

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
                    max_papers=search_config.max_papers * 2,
                    days_lookback=search_config.days_lookback
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

            # RSS
            if "rss" in search_config.sources:
                task = progress.add_task("Searching RSS feeds...", total=None)
                papers = self.rss_searcher.search(
                    keywords=search_config.keywords,
                    journals=search_config.journals,
                    max_papers=search_config.max_papers * 2,
                    days_lookback=search_config.days_lookback
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

            # bioRxiv
            if "biorxiv" in search_config.sources:
                task = progress.add_task("Searching bioRxiv...", total=None)
                papers = self.biorxiv_searcher.search(
                    keywords=search_config.keywords,
                    max_papers=search_config.max_papers * 2,
                    days_lookback=search_config.days_lookback
                )
                all_papers.extend(papers)
                progress.update(task, completed=True)

        console.print(f"[green]Found {len(all_papers)} papers total[/green]")
        return all_papers

    def filter_papers(self, papers: list[Paper]) -> list[Paper]:
        """Filter out duplicates and limit to max_papers."""
        # Remove duplicates
        unique_papers = self.dedup_checker.filter_duplicates(papers)
        console.print(f"[yellow]After deduplication: {len(unique_papers)} papers[/yellow]")

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
        """Download PDFs for open access papers.

        Note: Papers are kept even if PDF download fails - content will be
        fetched via Jina Reader during processing.
        """
        console.print("[cyan]Downloading papers...[/cyan]")

        for paper in papers:
            if paper.is_open_access or paper.pdf_url:
                self.downloader.download(paper)  # Updates paper.local_pdf_path if successful

        pdf_count = len([p for p in papers if p.local_pdf_path])
        console.print(f"[green]Downloaded {pdf_count} PDFs[/green]")

        # Return all papers - Jina Reader will be used for those without PDFs
        return papers

    def process_papers(self, papers: list[Paper]) -> tuple[list[ProcessedPaper], dict]:
        """Process papers with AI (summarize, translate).

        Content is fetched in this priority:
        1. Local PDF (if downloaded)
        2. Jina Reader (web-based content via r.jina.ai)
        3. Abstract only (fallback)

        Returns:
            Tuple of (processed_papers, body_texts_dict)
        """
        processed = []
        body_texts = {}

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

                try:
                    body_text = ""
                    figures = []

                    # Method 1: Parse local PDF if available
                    if paper.local_pdf_path:
                        console.print(f"[cyan]Parsing PDF: {paper.title[:40]}...[/cyan]")
                        parsed = self.pdf_parser.parse_paper(paper)
                        body_text = parsed.get("text", "")
                        figures = parsed.get("figures", [])

                    # Method 2: Use Jina Reader for web-based content
                    if not body_text:
                        console.print(f"[cyan]Fetching via Jina Reader: {paper.title[:40]}...[/cyan]")
                        content = self.content_fetcher.fetch_content(paper)
                        body_text = content.get("text", "")
                        figures = content.get("figures", [])

                    # Store body text for figure explanation
                    paper_id = paper.doi or paper.title
                    body_texts[paper_id] = body_text

                    # Summarize (will use abstract-only prompt if no body_text)
                    summary = self.summarizer.summarize(paper, body_text)

                    # Translate abstract
                    translation = []
                    if self.config.ai.translate_abstract and paper.abstract:
                        translation = self.translator.translate(paper.abstract)

                    processed_paper = ProcessedPaper(
                        paper=paper,
                        summary_korean=summary,
                        abstract_translation=translation,
                        figures=figures,
                        llm_provider=self.config.ai.llm_provider
                    )
                    processed.append(processed_paper)

                except Exception as e:
                    console.print(f"[red]Error processing {paper.title[:40]}: {e}[/red]")
                    import traceback
                    traceback.print_exc()
                    # Add with minimal processing
                    processed.append(ProcessedPaper(
                        paper=paper,
                        summary_korean=f"(처리 오류: {str(e)})",
                        abstract_translation=[],
                        figures=[]
                    ))

                progress.update(task, completed=True)

        return processed, body_texts

    def generate_figure_explanations(
        self,
        processed_papers: list[ProcessedPaper],
        body_texts: dict
    ) -> dict:
        """Generate figure explanations for papers.

        Only generates explanations when:
        - Paper has extracted figures (from PDF)
        - OR paper has figure legends in body text
        """
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
                    console.print(f"[yellow]Skipping figure explanation (no figures): {pp.paper.title[:40]}...[/yellow]")
                    continue

                # Combine legends for explanation
                legend_text = "\n".join([
                    f"Figure {l['figure_num']}: {l['legend']}"
                    for l in legends
                ]) if legends else ""

                # Generate explanation
                explanation = self.figure_explanation_generator.generate_explanation(
                    pp.paper,
                    pp.summary_korean,
                    legend_text
                )
                explanations[paper_id] = explanation
            except Exception as e:
                console.print(f"[yellow]Figure explanation error: {e}[/yellow]")

        return explanations

    def generate_output(
        self,
        processed_papers: list[ProcessedPaper],
        figure_explanations: dict
    ) -> dict:
        """Generate output files (PDF, Obsidian)."""
        result = {}

        # Generate PDF
        if self.config.output.pdf_report:
            console.print("[cyan]Generating PDF report...[/cyan]")
            try:
                pdf_path = self.pdf_generator.generate_pdf(processed_papers, figure_explanations)
                result["pdf"] = pdf_path
                console.print(f"[green]PDF: {pdf_path}[/green]")
            except Exception as e:
                console.print(f"[red]PDF error: {e}[/red]")
                # Fallback to HTML
                try:
                    html_path = self.pdf_generator.generate_html_file(processed_papers, figure_explanations)
                    result["html"] = html_path
                    console.print(f"[yellow]HTML fallback: {html_path}[/yellow]")
                except Exception as e2:
                    console.print(f"[red]HTML error: {e2}[/red]")

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

        # 1. Search
        papers = self.search_papers()
        if not papers:
            console.print("[yellow]No papers found![/yellow]")
            return {"papers": 0}

        # 2. Filter
        papers = self.filter_papers(papers)
        if not papers:
            console.print("[yellow]No new papers after filtering![/yellow]")
            return {"papers": 0}

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
        processed, body_texts = self.process_papers(papers)

        # 5. Generate figure explanations
        figure_explanations = self.generate_figure_explanations(processed, body_texts)

        # 6. Generate output
        output = self.generate_output(processed, figure_explanations)

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
