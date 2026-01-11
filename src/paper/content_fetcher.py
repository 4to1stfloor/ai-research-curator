"""Fetch paper content using Jina Reader API."""

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from ..models import Paper


class JinaContentFetcher:
    """Fetch paper content using Jina Reader API (https://r.jina.ai/)."""

    JINA_BASE = "https://r.jina.ai/"

    def __init__(self, figures_dir: str | Path, timeout: int = 60):
        """
        Initialize content fetcher.

        Args:
            figures_dir: Directory to save downloaded figures
            timeout: Request timeout in seconds
        """
        self.figures_dir = Path(figures_dir)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain, text/markdown, */*",
        })

    def _get_paper_url(self, paper: Paper) -> Optional[str]:
        """Get the best URL for fetching paper content."""
        # Priority: PMC > DOI > URL
        if paper.pmcid:
            return f"https://pmc.ncbi.nlm.nih.gov/articles/{paper.pmcid}/"

        if paper.doi:
            # Check if it's a bioRxiv/medRxiv DOI
            if "10.1101" in paper.doi:
                return f"https://www.biorxiv.org/content/{paper.doi}"
            return f"https://doi.org/{paper.doi}"

        if paper.url:
            return paper.url

        return None

    def fetch_content(self, paper: Paper) -> dict:
        """
        Fetch paper content using Jina Reader.

        Args:
            paper: Paper object

        Returns:
            dict with keys: 'text' (markdown content), 'figures' (list of figure paths)
        """
        url = self._get_paper_url(paper)
        if not url:
            print(f"[Jina] No URL available for: {paper.title[:50]}...")
            return {"text": "", "figures": []}

        jina_url = f"{self.JINA_BASE}{url}"
        print(f"[Jina] Fetching: {url[:60]}...")

        try:
            response = self.session.get(jina_url, timeout=self.timeout)
            response.raise_for_status()
            markdown_content = response.text

            # Extract and download figures
            figures = self._extract_and_download_figures(markdown_content, paper)

            # Clean up the markdown content
            clean_text = self._clean_markdown(markdown_content)

            return {"text": clean_text, "figures": figures}

        except requests.exceptions.Timeout:
            print(f"[Jina] Timeout fetching: {url[:50]}...")
            return {"text": "", "figures": []}
        except requests.exceptions.RequestException as e:
            print(f"[Jina] Error fetching {url[:50]}: {e}")
            return {"text": "", "figures": []}

    def _extract_and_download_figures(
        self,
        markdown: str,
        paper: Paper
    ) -> list[dict]:
        """
        Extract figure URLs from markdown and download them.

        Args:
            markdown: Markdown content from Jina Reader
            paper: Paper object for naming

        Returns:
            List of {figure_num, path, caption}
        """
        figures = []

        # Pattern to match markdown images: ![alt](url)
        # Also look for figure references like "Figure 1" nearby
        img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        matches = re.findall(img_pattern, markdown)

        # Also look for linked images: [![alt](url)](link)
        linked_img_pattern = r'\[!\[([^\]]*)\]\(([^)]+)\)\]'
        linked_matches = re.findall(linked_img_pattern, markdown)

        all_matches = matches + linked_matches

        # Filter for actual figure images (not icons, logos, badges, etc.)
        figure_urls = []
        skip_patterns = [
            'icon', 'logo', 'button', 'inline', 'loading',
            'altmetric', 'hypothesis', 'twitter', 'facebook',
            'badge', 'widget', 'eval/', 'connect.biorxiv',
            'crossmark', 'orcid', 'creative-commons', 'ads/'
        ]

        for alt, url in all_matches:
            url_lower = url.lower()
            alt_lower = alt.lower()

            # Skip small images, icons, badges, etc.
            if any(skip in url_lower for skip in skip_patterns):
                continue
            if any(skip in alt_lower for skip in ['icon', 'logo', 'badge']):
                continue

            # Look for figure-related URLs
            if 'fig' in url_lower or 'figure' in alt_lower:
                figure_urls.append((alt, url))
            # Also include CDN images from PMC
            elif 'cdn.ncbi.nlm.nih.gov' in url:
                figure_urls.append((alt, url))
            # Include bioRxiv/medRxiv content images
            elif ('biorxiv.org/content' in url_lower or 'medrxiv.org/content' in url_lower) and ('full' in url_lower or 'embed' in url_lower):
                figure_urls.append((alt, url))

        # Download figures
        paper_id = self._sanitize_filename(paper.title[:50])

        for i, (alt, url) in enumerate(figure_urls, 1):
            try:
                # Determine figure number from alt text or URL
                fig_num = self._extract_figure_number(alt, url) or str(i)

                # Download figure
                fig_path = self._download_figure(url, paper_id, fig_num)
                if fig_path:
                    figures.append({
                        "figure_num": fig_num,
                        "path": str(fig_path),
                        "caption": alt,
                        "url": url
                    })
                    print(f"[Jina] Downloaded figure {fig_num}: {fig_path.name}")

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"[Jina] Error downloading figure: {e}")

        return figures

    def _extract_figure_number(self, alt: str, url: str) -> Optional[str]:
        """Extract figure number from alt text or URL."""
        # Try alt text first
        match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', alt)
        if match:
            return match.group(1)

        # Try URL
        match = re.search(r'fig(\d+[a-z]?)', url.lower())
        if match:
            return match.group(1)

        return None

    def _download_figure(
        self,
        url: str,
        paper_id: str,
        fig_num: str
    ) -> Optional[Path]:
        """Download a figure image."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Determine file extension
            content_type = response.headers.get('content-type', '')
            if 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            else:
                ext = '.jpg'

            # Also check URL for extension
            url_ext = Path(urlparse(url).path).suffix
            if url_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                ext = url_ext

            # Save figure
            filename = f"{paper_id}_fig{fig_num}{ext}"
            filepath = self.figures_dir / filename

            with open(filepath, 'wb') as f:
                f.write(response.content)

            return filepath

        except Exception as e:
            print(f"[Jina] Download error for {url[:50]}: {e}")
            return None

    def _clean_markdown(self, markdown: str) -> str:
        """Clean markdown content for summarization."""
        # Remove image markdown syntax but keep text
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', markdown)
        text = re.sub(r'\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)', '', text)

        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        # Remove navigation links and headers
        text = re.sub(r'\[.*?\]\(#[^)]+\)', '', text)

        return text.strip()

    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title."""
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\s+', '_', safe)
        return safe


def fetch_paper_content(paper: Paper, figures_dir: str | Path) -> dict:
    """
    Convenience function to fetch paper content.

    Args:
        paper: Paper object
        figures_dir: Directory to save figures

    Returns:
        dict with 'text' and 'figures' keys
    """
    fetcher = JinaContentFetcher(figures_dir)
    return fetcher.fetch_content(paper)
