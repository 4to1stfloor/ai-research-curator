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

            # Track seen figure numbers and URLs to avoid duplicates
            seen_fig_nums = set()
            seen_urls = set()

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

                    # Skip duplicate URLs
                    if img_src in seen_urls:
                        continue
                    seen_urls.add(img_src)

                    # Get figure caption
                    caption_elem = fig_elem.find(['figcaption', 'div'], class_=re.compile(r'caption|fig-caption'))
                    caption = caption_elem.get_text(strip=True) if caption_elem else ""

                    # Extract figure number
                    fig_num = str(i)
                    fig_match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', caption or str(fig_elem))
                    if fig_match:
                        fig_num = fig_match.group(1)

                    # Skip duplicate figure numbers
                    if fig_num in seen_fig_nums:
                        continue
                    seen_fig_nums.add(fig_num)

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
            figure_containers = []

            # Method 1: figure tags with data-test='figure' (Nature/Springer)
            data_test_figures = soup.find_all(attrs={'data-test': 'figure'})
            figure_containers.extend(data_test_figures)

            # Method 2: figure tags (generic)
            figure_tags = soup.find_all('figure')
            for fig in figure_tags:
                if fig not in figure_containers:
                    figure_containers.append(fig)

            # Method 3: divs with figure-related classes
            class_figures = soup.find_all(['div'], class_=re.compile(
                r'fig|figure|image-container|article-fig', re.IGNORECASE
            ))
            for fig in class_figures:
                if fig not in figure_containers:
                    figure_containers.append(fig)

            # Track seen figures to avoid duplicates
            seen_fig_nums = set()
            seen_urls = set()

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

                    # Skip if URL already processed
                    if img_src in seen_urls:
                        continue
                    seen_urls.add(img_src)

                    # Get caption
                    caption_elem = container.find(['figcaption', 'div'], class_=re.compile(r'caption', re.IGNORECASE))
                    caption = caption_elem.get_text(strip=True) if caption_elem else ""

                    # Figure number
                    fig_num = str(i)
                    fig_match = re.search(r'[Ff]ig(?:ure)?\.?\s*(\d+[A-Za-z]?)', caption or img.get('alt', ''))
                    if fig_match:
                        fig_num = fig_match.group(1)

                    # Skip if figure number already processed
                    if fig_num in seen_fig_nums:
                        continue
                    seen_fig_nums.add(fig_num)

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

        Priority for figures (tries each until successful):
        1. PMC (if PMCID available)
        2. bioRxiv/medRxiv (if 10.1101 DOI)
        3. DOI resolution (for other publishers)
        4. Journal-specific extraction

        Args:
            paper: Paper object

        Returns:
            dict with keys: 'text' (content), 'figures' (list of figure dicts), 'source'
        """
        text = ""
        figures = []
        source = "unknown"

        # Extract DOI from URL if not available
        if not paper.doi and paper.url:
            extracted_doi = self._extract_doi_from_url(paper.url)
            if extracted_doi:
                paper.doi = extracted_doi
                print(f"[ContentFetcher] Extracted DOI from URL: {extracted_doi}")

        # Method 1: Try PMC first (most reliable for open access)
        if paper.pmcid:
            print(f"[ContentFetcher] Trying PMC source: {paper.pmcid}")
            figures = self.figure_fetcher.fetch_from_pmc(paper.pmcid, paper.title)
            if figures:
                source = "pmc"

        # Method 2: Try bioRxiv/medRxiv
        if not figures and paper.doi and "10.1101" in paper.doi:
            print(f"[ContentFetcher] Trying bioRxiv source: {paper.doi}")
            figures = self.figure_fetcher.fetch_from_biorxiv(paper.doi, paper.title)
            if figures:
                source = "biorxiv"

        # Method 3: Try DOI resolution (publisher page)
        if not figures and paper.doi:
            print(f"[ContentFetcher] Trying DOI source: {paper.doi}")
            figures = self.figure_fetcher.fetch_from_doi(paper.doi, paper.title)
            if figures:
                source = "doi"

        # Method 4: Try journal-specific extraction (PLOS, etc.)
        if not figures and paper.doi:
            figures = self._fetch_from_journal_specific(paper)
            if figures:
                source = "journal"

        # Fetch text content (from abstract if no other source)
        if paper.abstract:
            text = paper.abstract

        return {
            "text": text,
            "figures": figures,
            "figure_legends": self._extract_figure_legends(figures),
            "source": source
        }

    def _extract_doi_from_url(self, url: str) -> Optional[str]:
        """
        Extract DOI from paper URL.

        Args:
            url: Paper URL

        Returns:
            DOI string if found, None otherwise
        """
        if not url:
            return None

        # PLOS pattern: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013867
        plos_match = re.search(r'journals\.plos\.org/\w+/article\?id=(10\.\d+/[^\s&]+)', url)
        if plos_match:
            return plos_match.group(1)

        # Nature pattern: https://www.nature.com/articles/s41586-024-07855-6
        nature_match = re.search(r'nature\.com/articles/(s\d+-\d+-\d+-\w+)', url)
        if nature_match:
            return f"10.1038/{nature_match.group(1)}"

        # Science pattern: https://www.science.org/doi/10.1126/science.xxx
        science_match = re.search(r'science\.org/doi/(10\.\d+/[^\s&]+)', url)
        if science_match:
            return science_match.group(1)

        # Cell/Elsevier pattern: https://www.cell.com/cell/fulltext/S0092-8674(xx)xxxxx-x
        # These use PII, not DOI directly

        # BMC/Springer pattern: https://bmcgenomics.biomedcentral.com/articles/10.1186/s12864-024-xxxx
        bmc_match = re.search(r'biomedcentral\.com/articles/(10\.\d+/[^\s&]+)', url)
        if bmc_match:
            return bmc_match.group(1)

        # eLife pattern: https://elifesciences.org/articles/xxxxx
        elife_match = re.search(r'elifesciences\.org/articles/(\d+)', url)
        if elife_match:
            return f"10.7554/eLife.{elife_match.group(1)}"

        # Generic DOI in URL
        generic_match = re.search(r'(10\.\d{4,}/[^\s&]+)', url)
        if generic_match:
            return generic_match.group(1)

        return None

    def _fetch_from_journal_specific(self, paper: Paper) -> list[dict]:
        """
        Try journal-specific figure extraction patterns.

        Args:
            paper: Paper object

        Returns:
            List of figure dicts
        """
        if not paper.doi:
            return []

        doi = paper.doi
        figures = []

        try:
            # PLOS journals
            if "10.1371/journal" in doi:
                figures = self._fetch_plos_figures(doi, paper.title)

            # eLife
            elif "10.7554/eLife" in doi:
                figures = self._fetch_elife_figures(doi, paper.title)

            # Genome Biology / BMC
            elif "10.1186" in doi:
                figures = self._fetch_bmc_figures(doi, paper.title)

        except Exception as e:
            print(f"[ContentFetcher] Journal-specific extraction failed: {e}")

        return figures

    def _fetch_plos_figures(self, doi: str, paper_title: str) -> list[dict]:
        """Fetch figures from PLOS journals."""
        figures = []
        paper_id = re.sub(r'[<>:"/\\|?*]', '', paper_title)[:50].replace(' ', '_')
        paper_dir = self.figures_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        # Determine journal from DOI
        journal_map = {
            'pcbi': 'ploscompbiol',
            'pone': 'plosone',
            'pbio': 'plosbiology',
            'pgen': 'plosgenetics',
            'pmed': 'plosmedicine',
            'ppat': 'plospathogens',
            'pntd': 'plosntds',
        }

        # Extract journal code from DOI (e.g., 10.1371/journal.pcbi.1013867)
        journal_code = 'ploscompbiol'  # default
        doi_match = re.search(r'journal\.(\w+)\.', doi)
        if doi_match:
            code = doi_match.group(1)
            journal_code = journal_map.get(code, 'plosone')

        try:
            url = f"https://journals.plos.org/{journal_code}/article?id={doi}"
            print(f"[PLOS] Fetching figures from: {url}")

            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                print(f"[PLOS] Page not found, status: {response.status_code}")
                return figures

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find figure sections (PLOS uses div.figure)
            fig_sections = soup.find_all('div', class_='figure')
            print(f"[PLOS] Found {len(fig_sections)} figure sections")

            seen_nums = set()
            for i, fig in enumerate(fig_sections[:10], 1):
                try:
                    img = fig.find('img')
                    if not img:
                        continue

                    img_src = img.get('src') or img.get('data-src')
                    if not img_src:
                        continue

                    # Skip small icons
                    if 'orcid' in img_src or 'logo' in img_src:
                        continue

                    # Make absolute URL
                    if img_src.startswith('//'):
                        img_src = 'https:' + img_src
                    elif img_src.startswith('/'):
                        img_src = 'https://journals.plos.org' + img_src
                    elif not img_src.startswith('http'):
                        img_src = f"https://journals.plos.org/{journal_code}/" + img_src

                    # Get figure number from URL or caption
                    fig_num = str(i)
                    # PLOS URL pattern: .../10.1371/journal.pcbi.1013867.g001
                    url_match = re.search(r'\.g(\d+)', img_src)
                    if url_match:
                        fig_num = url_match.group(1).lstrip('0') or '1'

                    # Get caption
                    caption = ""
                    caption_elem = fig.find('figcaption') or fig.find('p', class_='caption')
                    if caption_elem:
                        caption = caption_elem.get_text(strip=True)

                    if fig_num in seen_nums:
                        continue
                    seen_nums.add(fig_num)

                    # Download with larger size
                    # Change size=inline to size=large for better quality
                    img_src_large = img_src.replace('size=inline', 'size=large')

                    filepath = paper_dir / f"fig_{fig_num}.png"

                    img_response = self.session.get(img_src_large, timeout=30)
                    if img_response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            f.write(img_response.content)
                        figures.append({
                            "figure_num": fig_num,
                            "path": str(filepath),
                            "caption": caption[:500],
                            "url": img_src_large
                        })
                        print(f"[PLOS] Downloaded Figure {fig_num}")

                except Exception as e:
                    print(f"[PLOS] Error processing figure: {e}")
                    continue

        except Exception as e:
            print(f"[PLOS] Failed: {e}")

        return figures

    def _fetch_elife_figures(self, doi: str, paper_title: str) -> list[dict]:
        """Fetch figures from eLife using IIIF image server."""
        figures = []
        paper_id = re.sub(r'[<>:"/\\|?*]', '', paper_title)[:50].replace(' ', '_')
        paper_dir = self.figures_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        # Extract article ID from DOI (e.g., 10.7554/eLife.92991 -> 92991)
        article_id = doi.split(".")[-1]

        url = f"https://elifesciences.org/articles/{article_id}"
        print(f"[eLife] Fetching figures from: {url}")

        response = self.session.get(url, timeout=self.timeout)
        if response.status_code != 200:
            return figures

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all figure elements with captioned-asset class
        fig_elements = soup.find_all('figure', class_='captioned-asset')
        print(f"[eLife] Found {len(fig_elements)} figure elements")

        seen_nums = set()
        for fig in fig_elements:
            # Get img and extract figure number from src URL
            img = fig.find('img')
            if not img:
                continue

            img_src = img.get('src', '')
            # Extract figure number from URL pattern: elife-92991-fig1-v1.tif
            fig_num_match = re.search(r'elife-\d+-fig(\d+)', img_src)
            if not fig_num_match:
                continue

            fig_num = fig_num_match.group(1)
            if fig_num in seen_nums:
                continue
            seen_nums.add(fig_num)

            # Build IIIF URL for full-size image (1500px width)
            img_url = f"https://iiif.elifesciences.org/lax:{article_id}%2Felife-{article_id}-fig{fig_num}-v1.tif/full/1500,/0/default.jpg"

            # Get caption
            caption = ""
            caption_elem = fig.find('figcaption')
            if caption_elem:
                caption = caption_elem.get_text(strip=True)[:500]

            # Download figure
            filepath = paper_dir / f"fig_{fig_num}.jpg"

            img_response = self.session.get(img_url, timeout=30)
            if img_response.status_code == 200 and len(img_response.content) > 1000:
                with open(filepath, 'wb') as f:
                    f.write(img_response.content)
                figures.append({
                    "figure_num": fig_num,
                    "path": str(filepath),
                    "caption": caption,
                    "url": img_url
                })
                print(f"[eLife] Downloaded Figure {fig_num}")

        return figures

    def _fetch_bmc_figures(self, doi: str, paper_title: str) -> list[dict]:
        """Fetch figures from BMC/Springer journals."""
        # Similar to DOI fetch but with BMC-specific patterns
        return self.figure_fetcher.fetch_from_doi(doi, paper_title)

    def fetch_abstract_from_doi(self, doi: str) -> Optional[str]:
        """
        Fetch abstract from DOI by resolving to publisher page.

        Args:
            doi: Paper DOI

        Returns:
            Abstract text or None
        """
        if not doi:
            return None

        try:
            doi_url = f"https://doi.org/{doi}"
            response = self.session.get(doi_url, timeout=15, allow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Try common abstract patterns
            abstract = None

            # Pattern 1: Meta tag (most common)
            meta_abstract = soup.find('meta', {'name': 'description'})
            if meta_abstract and meta_abstract.get('content'):
                abstract = meta_abstract['content']

            # Pattern 2: DC.description meta
            if not abstract:
                dc_abstract = soup.find('meta', {'name': 'DC.description'})
                if dc_abstract and dc_abstract.get('content'):
                    abstract = dc_abstract['content']

            # Pattern 3: Abstract section
            if not abstract:
                abstract_section = soup.find(['section', 'div'], class_=re.compile(r'abstract', re.I))
                if abstract_section:
                    # Remove heading
                    heading = abstract_section.find(['h2', 'h3', 'h4'])
                    if heading:
                        heading.decompose()
                    abstract = abstract_section.get_text(strip=True)

            # Pattern 4: ID="abstract"
            if not abstract:
                abstract_elem = soup.find(id=re.compile(r'abstract', re.I))
                if abstract_elem:
                    abstract = abstract_elem.get_text(strip=True)

            if abstract and len(abstract) > 100:  # Sanity check
                print(f"[ContentFetcher] Fetched abstract from DOI: {doi[:30]}...")
                return abstract[:3000]  # Limit length

        except Exception as e:
            print(f"[ContentFetcher] Failed to fetch abstract from DOI: {e}")

        return None

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
