"""Paper PDF downloader."""

import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Paper

# Unpaywall API for finding open access versions
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"


class PaperDownloader:
    """Download papers from various sources."""

    def __init__(
        self,
        output_dir: str | Path,
        email: Optional[str] = None
    ):
        """
        Initialize downloader.

        Args:
            output_dir: Directory to save downloaded papers
            email: Email for Unpaywall API (required for OA lookup)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.email = email

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AutoPaperScraper/1.0 (mailto:{})".format(
                email or "anonymous@example.com"
            )
        })

    def _sanitize_filename(self, title: str, max_length: int = 100) -> str:
        """Create safe filename from title."""
        # Remove invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        # Replace spaces with underscores
        safe = re.sub(r'\s+', '_', safe)
        # Limit length
        if len(safe) > max_length:
            safe = safe[:max_length]
        return safe

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _check_unpaywall(self, doi: str) -> Optional[str]:
        """
        Check Unpaywall for open access PDF URL.

        Args:
            doi: Paper DOI

        Returns:
            PDF URL if available, None otherwise
        """
        if not self.email or not doi:
            return None

        try:
            url = UNPAYWALL_API.format(doi=doi)
            response = self.session.get(url, params={"email": self.email})

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            # Try to get best OA location
            best_oa = data.get("best_oa_location")
            if best_oa:
                pdf_url = best_oa.get("url_for_pdf")
                if pdf_url:
                    return pdf_url

                # Try direct URL
                landing_url = best_oa.get("url")
                if landing_url:
                    return landing_url

            return None

        except Exception as e:
            print(f"Unpaywall error for {doi}: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def _download_pdf(self, url: str, output_path: Path) -> bool:
        """
        Download PDF from URL.

        Args:
            url: PDF URL
            output_path: Path to save PDF

        Returns:
            True if successful
        """
        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                print(f"Not a PDF: {content_type}")
                return False

            # Save file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify file is valid PDF
            with open(output_path, 'rb') as f:
                header = f.read(5)
                if header != b'%PDF-':
                    os.remove(output_path)
                    return False

            return True

        except Exception as e:
            print(f"Download error: {e}")
            if output_path.exists():
                os.remove(output_path)
            return False

    def download(self, paper: Paper) -> Optional[str]:
        """
        Download paper PDF.

        Args:
            paper: Paper to download

        Returns:
            Path to downloaded PDF, or None if failed
        """
        # Create filename
        filename = self._sanitize_filename(paper.title) + ".pdf"
        output_path = self.output_dir / filename

        # Skip if already downloaded
        if output_path.exists():
            print(f"Already downloaded: {paper.title[:50]}...")
            paper.local_pdf_path = str(output_path)
            return str(output_path)

        # Try different sources
        pdf_urls = []

        # 1. Direct PDF URL from source
        if paper.pdf_url:
            pdf_urls.append(paper.pdf_url)

        # 2. PMC PDF
        if paper.pmcid:
            pdf_urls.append(f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmcid}/pdf/")

        # 3. Unpaywall
        if paper.doi:
            unpaywall_url = self._check_unpaywall(paper.doi)
            if unpaywall_url:
                pdf_urls.append(unpaywall_url)

        # 4. bioRxiv/medRxiv direct
        if paper.biorxiv_id:
            pdf_urls.append(f"https://www.biorxiv.org/content/{paper.biorxiv_id}.full.pdf")
            pdf_urls.append(f"https://www.medrxiv.org/content/{paper.biorxiv_id}.full.pdf")

        # Try each URL
        for url in pdf_urls:
            print(f"Trying: {url[:80]}...")
            if self._download_pdf(url, output_path):
                paper.local_pdf_path = str(output_path)
                print(f"Downloaded: {paper.title[:50]}...")
                return str(output_path)
            time.sleep(1)  # Rate limiting

        print(f"Could not download: {paper.title[:50]}...")
        return None

    def download_papers(
        self,
        papers: list[Paper],
        skip_failed: bool = True
    ) -> list[Paper]:
        """
        Download multiple papers.

        Args:
            papers: List of papers to download
            skip_failed: If True, continue on download failures

        Returns:
            List of papers with downloaded PDFs
        """
        downloaded = []

        for paper in papers:
            try:
                path = self.download(paper)
                if path:
                    downloaded.append(paper)
                elif not skip_failed:
                    raise Exception(f"Failed to download: {paper.title}")
            except Exception as e:
                if not skip_failed:
                    raise
                print(f"Skipping: {e}")

            time.sleep(2)  # Rate limiting between papers

        return downloaded


# ============================================================================
# TODO: Institutional Authentication Support
# ============================================================================
# The following section is prepared for future implementation of institutional
# authentication for accessing paywalled papers.
#
# class InstitutionalDownloader(PaperDownloader):
#     """Download papers using institutional authentication."""
#
#     def __init__(
#         self,
#         output_dir: str | Path,
#         institution: str,  # "ncc" or "snu"
#         proxy_url: Optional[str] = None,
#         vpn_config: Optional[dict] = None,
#     ):
#         """
#         Initialize institutional downloader.
#
#         Args:
#             output_dir: Directory to save downloaded papers
#             institution: Institution code ("ncc" for National Cancer Center,
#                         "snu" for Seoul National University)
#             proxy_url: Proxy URL for institutional access
#             vpn_config: VPN configuration for institutional access
#         """
#         super().__init__(output_dir)
#         self.institution = institution
#         self.proxy_url = proxy_url
#         self.vpn_config = vpn_config
#
#     def _get_institutional_url(self, doi: str) -> Optional[str]:
#         """
#         Get institutional access URL for a paper.
#
#         For NCC (National Cancer Center):
#         - EZproxy URL format
#
#         For SNU (Seoul National University):
#         - Library proxy format
#         """
#         # NCC proxy pattern (example)
#         if self.institution == "ncc":
#             return f"https://doi.org.proxy.ncc.re.kr/{doi}"
#
#         # SNU proxy pattern (example)
#         elif self.institution == "snu":
#             return f"https://doi.org.libproxy.snu.ac.kr/{doi}"
#
#         return None
#
#     def _authenticate(self) -> bool:
#         """Authenticate with institutional proxy."""
#         # TODO: Implement institutional authentication
#         # This may involve:
#         # 1. VPN connection
#         # 2. Proxy authentication
#         # 3. Cookie-based authentication
#         pass
#
# ============================================================================
