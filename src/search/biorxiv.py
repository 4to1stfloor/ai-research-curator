"""bioRxiv/medRxiv API searcher."""

from datetime import datetime, timedelta
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Paper, PaperSource

# bioRxiv API base URL
BIORXIV_API_URL = "https://api.biorxiv.org/details"


class BioRxivSearcher:
    """Search papers using bioRxiv/medRxiv API."""

    def __init__(self):
        """Initialize bioRxiv searcher."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AutoPaperScraper/1.0"
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _fetch_papers(
        self,
        server: str,
        start_date: str,
        end_date: str,
        cursor: int = 0
    ) -> dict:
        """
        Fetch papers from bioRxiv/medRxiv API.

        Args:
            server: "biorxiv" or "medrxiv"
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            cursor: Pagination cursor

        Returns:
            API response dictionary
        """
        url = f"{BIORXIV_API_URL}/{server}/{start_date}/{end_date}/{cursor}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def _parse_paper(self, data: dict, server: str) -> Optional[Paper]:
        """Parse a single paper from API response."""
        try:
            # Basic info
            title = data.get("title", "").strip()
            if not title:
                return None

            doi = data.get("doi")
            biorxiv_id = data.get("biorxiv_doi") or doi

            # Authors
            authors_str = data.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()]

            # Date
            pub_date = None
            date_str = data.get("date")
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

            # Abstract
            abstract = data.get("abstract", "")

            # URL
            url = f"https://www.{server}.org/content/{doi}" if doi else ""

            # PDF URL
            pdf_url = f"https://www.{server}.org/content/{doi}.full.pdf" if doi else None

            # Category/Keywords
            category = data.get("category", "")
            keywords = [category] if category else []

            return Paper(
                title=title,
                doi=doi,
                biorxiv_id=biorxiv_id,
                authors=authors,
                journal=f"{server.capitalize()} (preprint)",
                publication_date=pub_date,
                abstract=abstract,
                keywords=keywords,
                url=url,
                pdf_url=pdf_url,
                source=PaperSource.BIORXIV,
                is_open_access=True,  # All preprints are open access
            )

        except Exception as e:
            print(f"Error parsing bioRxiv paper: {e}")
            return None

    def _matches_keywords(self, paper: Paper, keywords: list[str]) -> bool:
        """Check if paper matches any of the keywords."""
        text = (paper.title + " " + paper.abstract).lower()
        return any(kw.lower() in text for kw in keywords)

    def search(
        self,
        keywords: list[str],
        max_papers: int = 10,
        days_lookback: int = 7,
        include_medrxiv: bool = True
    ) -> list[Paper]:
        """
        Search bioRxiv/medRxiv for papers.

        Args:
            keywords: Keywords to filter by
            max_papers: Maximum number of papers to return
            days_lookback: Number of days to look back
            include_medrxiv: Whether to include medRxiv

        Returns:
            List of Paper objects
        """
        papers = []

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_lookback)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        servers = ["biorxiv"]
        if include_medrxiv:
            servers.append("medrxiv")

        for server in servers:
            print(f"[{server.capitalize()}] Searching {start_str} to {end_str}...")

            cursor = 0
            server_papers = []

            while len(server_papers) < max_papers * 2:  # Get extra for filtering
                try:
                    response = self._fetch_papers(server, start_str, end_str, cursor)
                except Exception as e:
                    print(f"[{server.capitalize()}] API error: {e}")
                    break

                collection = response.get("collection", [])
                if not collection:
                    break

                for item in collection:
                    paper = self._parse_paper(item, server)
                    if paper and self._matches_keywords(paper, keywords):
                        server_papers.append(paper)

                # Check if more results
                messages = response.get("messages", [])
                if messages:
                    total = int(messages[0].get("total", 0))
                    if cursor + len(collection) >= total:
                        break

                cursor += len(collection)

                # Limit API calls
                if cursor > 500:
                    break

            print(f"[{server.capitalize()}] Found {len(server_papers)} matching papers")
            papers.extend(server_papers)

        # Sort by date (newest first)
        papers.sort(key=lambda p: p.publication_date or datetime.min, reverse=True)

        return papers[:max_papers]
