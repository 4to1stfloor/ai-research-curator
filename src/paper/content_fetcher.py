"""Fetch paper content and figures from various sources."""

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..models import Paper


class FigureFetcher:
    """Fetch figures from various paper sources."""

    def __init__(self, figures_dir: str | Path, timeout: int = 30):
        """
        Initialize figure fetcher.

        Args:
            figures_dir: Directory to save downloaded figures
            timeout: Request timeout in seconds
        """
        self.figures_dir = Path(figures_dir)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title."""
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:50]

    def _download_image(self, url: str, filepath: Path) -> bool:
        """Download an image from URL."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type and 'octet-stream' not in content_type:
                return False

            with open(filepath, 'wb') as f:
                f.write(response.content)

            # Verify it's a valid image (check magic bytes)
            with open(filepath, 'rb') as f:
                header = f.read(8)
                # PNG, JPEG, GIF, WebP signatures
                valid_signatures = [
                    b'\x89PNG',  # PNG
                    b'\xff\xd8\xff',  # JPEG
                    b'GIF8',  # GIF
                    b'RIFF',  # WebP
                ]
                if not any(header.startswith(sig) for sig in valid_signatures):
                    filepath.unlink()
                    return False

            return True
        except Exception as e:
            print(f"[FigureFetcher] Download error: {e}")
            if filepath.exists():
                filepath.unlink()
            return False

    def fetch_from_pmc(self, pmcid: str, paper_title: str) -> list[dict]:
        """
        Fetch figures from PMC (PubMed Central).

        PMC provides figures directly on the article page.

        Args:
            pmcid: PMC ID (e.g., "PMC11839351")
            paper_title: Paper title for naming

        Returns:
            List of {figure_num, path, caption}
        """
        figures = []
        paper_id = self._sanitize_filename(paper_title)
        paper_dir = self.figures_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        try:
            # PMC article page
            url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
            print(f"[PMC] Fetching figures from: {url}")

            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find figure elements
            # PMC uses <figure> elements or <div class="fig">
            figure_elements = soup.find_all(['figure', 'div'], class_=re.compile(r'fig'))

            for i, fig_elem in enumerate(figure_elements, 1):
                try:
                    # Find image
                    img = fig_elem.find('img')
                    if not img:
                        continue

                    img_src = img.get('src') or img.get('data-src')
                    if not img_src:
                        continue

                    # Make absolute URL
                    if img_src.startswith('//'):
                        img_src = 'https:' + img_src
                    elif img_src.startswith('/'):
                        img_src = 'https://www.ncbi.nlm.nih.gov' + img_src

                    # Get figure caption
                    caption_elem = fig_elem.find(['figcaption', 'div'], class_=re.compile(r'caption|fig-caption'))
                    caption = caption_elem.get_text(strip=True) if caption_elem else ""

                    # Extract figure number
                    fig_num = str(i)
                    fig_match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', caption or str(fig_elem))
                    if fig_match:
                        fig_num = fig_match.group(1)

                    # Download figure
                    ext = Path(urlparse(img_src).path).suffix or '.jpg'
                    filename = f"fig_{fig_num}{ext}"
                    filepath = paper_dir / filename

                    if self._download_image(img_src, filepath):
                        figures.append({
                            "figure_num": fig_num,
                            "path": str(filepath),
                            "caption": caption[:500],
                            "url": img_src
                        })
                        print(f"[PMC] Downloaded Figure {fig_num}")

                    time.sleep(0.3)  # Rate limiting

                except Exception as e:
                    print(f"[PMC] Error processing figure: {e}")
                    continue

        except Exception as e:
            print(f"[PMC] Error fetching from PMC: {e}")

        return figures

    def fetch_from_biorxiv(self, doi: str, paper_title: str) -> list[dict]:
        """
        Fetch figures from bioRxiv/medRxiv.

        bioRxiv provides figure images on the article page.

        Args:
            doi: DOI (e.g., "10.1101/2023.10.25.564058")
            paper_title: Paper title for naming

        Returns:
            List of {figure_num, path, caption}
        """
        figures = []
        paper_id = self._sanitize_filename(paper_title)
        paper_dir = self.figures_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        # Try both bioRxiv and medRxiv
        base_urls = [
            f"https://www.biorxiv.org/content/{doi}",
            f"https://www.medrxiv.org/content/{doi}"
        ]

        for base_url in base_urls:
            try:
                # Use the .full version which has all figures
                url = f"{base_url}.full"
                print(f"[bioRxiv] Fetching figures from: {url}")

                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 403:
                    print(f"[bioRxiv] Access denied (Cloudflare), trying API...")
                    continue
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # bioRxiv uses <div class="fig"> for figures
                figure_divs = soup.find_all('div', class_='fig')

                for i, fig_div in enumerate(figure_divs, 1):
                    try:
                        # Find image link or img
                        img_link = fig_div.find('a', class_='fig-inline-img-wrapper')
                        if img_link:
                            img_src = img_link.get('href')
                        else:
                            img = fig_div.find('img')
                            img_src = img.get('src') if img else None

                        if not img_src:
                            continue

                        # Make absolute URL
                        if img_src.startswith('/'):
                            parsed = urlparse(base_url)
                            img_src = f"{parsed.scheme}://{parsed.netloc}{img_src}"

                        # Get figure caption
                        caption_elem = fig_div.find('div', class_='fig-caption')
                        caption = caption_elem.get_text(strip=True) if caption_elem else ""

                        # Extract figure number
                        fig_num = str(i)
                        fig_match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', caption or str(fig_div))
                        if fig_match:
                            fig_num = fig_match.group(1)

                        # Download figure
                        ext = Path(urlparse(img_src).path).suffix or '.jpg'
                        filename = f"fig_{fig_num}{ext}"
                        filepath = paper_dir / filename

                        if self._download_image(img_src, filepath):
                            figures.append({
                                "figure_num": fig_num,
                                "path": str(filepath),
                                "caption": caption[:500],
                                "url": img_src
                            })
                            print(f"[bioRxiv] Downloaded Figure {fig_num}")

                        time.sleep(0.3)

                    except Exception as e:
                        print(f"[bioRxiv] Error processing figure: {e}")
                        continue

                if figures:
                    break  # Found figures, don't try other URLs

            except requests.exceptions.RequestException as e:
                print(f"[bioRxiv] Request error: {e}")
                continue

        return figures

    def fetch_from_doi(self, doi: str, paper_title: str) -> list[dict]:
        """
        Fetch figures by resolving DOI to publisher page.

        Args:
            doi: Paper DOI
            paper_title: Paper title for naming

        Returns:
            List of {figure_num, path, caption}
        """
        figures = []
        paper_id = self._sanitize_filename(paper_title)
        paper_dir = self.figures_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        try:
            # Resolve DOI with shorter timeout
            doi_url = f"https://doi.org/{doi}"
            print(f"[DOI] Resolving: {doi_url}")

            response = self.session.get(doi_url, timeout=15, allow_redirects=True)
            response.raise_for_status()

            final_url = response.url
            print(f"[DOI] Redirected to: {final_url}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Generic figure extraction
            # Look for common figure patterns across publishers
            figure_containers = soup.find_all(['figure', 'div'], class_=re.compile(
                r'fig|figure|image-container|article-fig', re.IGNORECASE
            ))

            for i, container in enumerate(figure_containers[:10], 1):  # Limit to 10 figures
                try:
                    img = container.find('img')
                    if not img:
                        continue

                    img_src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if not img_src:
                        continue

                    # Skip small images (icons, logos)
                    width = img.get('width', '0')
                    height = img.get('height', '0')
                    try:
                        if int(width) < 100 or int(height) < 100:
                            continue
                    except (ValueError, TypeError):
                        pass

                    # Make absolute URL
                    if img_src.startswith('//'):
                        img_src = 'https:' + img_src
                    elif img_src.startswith('/'):
                        parsed = urlparse(final_url)
                        img_src = f"{parsed.scheme}://{parsed.netloc}{img_src}"

                    # Get caption
                    caption_elem = container.find(['figcaption', 'div'], class_=re.compile(r'caption', re.IGNORECASE))
                    caption = caption_elem.get_text(strip=True) if caption_elem else ""

                    # Figure number
                    fig_num = str(i)
                    fig_match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', caption or img.get('alt', ''))
                    if fig_match:
                        fig_num = fig_match.group(1)

                    # Download
                    ext = Path(urlparse(img_src).path).suffix or '.jpg'
                    filename = f"fig_{fig_num}{ext}"
                    filepath = paper_dir / filename

                    if self._download_image(img_src, filepath):
                        figures.append({
                            "figure_num": fig_num,
                            "path": str(filepath),
                            "caption": caption[:500],
                            "url": img_src
                        })
                        print(f"[DOI] Downloaded Figure {fig_num}")

                    time.sleep(0.3)

                except Exception as e:
                    print(f"[DOI] Error processing figure: {e}")
                    continue

        except Exception as e:
            print(f"[DOI] Error: {e}")

        return figures


class PaperContentFetcher:
    """Fetch paper content (text and figures) from various sources."""

    def __init__(self, figures_dir: str | Path, timeout: int = 30):
        """
        Initialize content fetcher.

        Args:
            figures_dir: Directory to save downloaded figures
            timeout: Request timeout in seconds
        """
        self.figures_dir = Path(figures_dir)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.figure_fetcher = FigureFetcher(figures_dir, timeout)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def fetch_content(self, paper: Paper) -> dict:
        """
        Fetch paper content and figures.

        Priority for figures:
        1. PMC (if PMCID available)
        2. bioRxiv/medRxiv (if 10.1101 DOI)
        3. DOI resolution (for other publishers)

        Args:
            paper: Paper object

        Returns:
            dict with keys: 'text' (content), 'figures' (list of figure dicts)
        """
        text = ""
        figures = []

        # Fetch figures based on source
        if paper.pmcid:
            print(f"[ContentFetcher] Using PMC source: {paper.pmcid}")
            figures = self.figure_fetcher.fetch_from_pmc(paper.pmcid, paper.title)

        elif paper.doi and "10.1101" in paper.doi:
            print(f"[ContentFetcher] Using bioRxiv source: {paper.doi}")
            figures = self.figure_fetcher.fetch_from_biorxiv(paper.doi, paper.title)

        elif paper.doi:
            print(f"[ContentFetcher] Using DOI source: {paper.doi}")
            figures = self.figure_fetcher.fetch_from_doi(paper.doi, paper.title)

        # Fetch text content (from abstract if no other source)
        if paper.abstract:
            text = paper.abstract

        return {
            "text": text,
            "figures": figures,
            "figure_legends": self._extract_figure_legends(figures)
        }

    def _extract_figure_legends(self, figures: list[dict]) -> str:
        """Extract figure legends from figures."""
        legends = []
        for fig in figures:
            if fig.get('caption'):
                legends.append(f"Figure {fig['figure_num']}: {fig['caption']}")
        return "\n\n".join(legends)


# Legacy alias for backward compatibility
class JinaContentFetcher(PaperContentFetcher):
    """Legacy alias for PaperContentFetcher."""

    JINA_BASE = "https://r.jina.ai/"

    def __init__(self, figures_dir: str | Path, timeout: int = 60):
        super().__init__(figures_dir, timeout)
        print("[Warning] JinaContentFetcher is deprecated, using PaperContentFetcher")


def fetch_paper_content(paper: Paper, figures_dir: str | Path) -> dict:
    """
    Convenience function to fetch paper content.

    Args:
        paper: Paper object
        figures_dir: Directory to save figures

    Returns:
        dict with 'text' and 'figures' keys
    """
    fetcher = PaperContentFetcher(figures_dir)
    return fetcher.fetch_content(paper)
