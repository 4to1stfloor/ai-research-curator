"""RSS feed parser for journal papers."""

from datetime import datetime, timedelta
from typing import Optional
from time import mktime

import feedparser

from ..models import Paper, PaperSource

# Journal RSS feeds
JOURNAL_RSS_FEEDS = {
    "Cell": "https://www.cell.com/cell/rss/current",
    "Nature": "https://www.nature.com/nature.rss",
    "Science": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    "Nature Methods": "https://www.nature.com/nmeth.rss",
    "Nature Biotechnology": "https://www.nature.com/nbt.rss",
    "Nature Medicine": "https://www.nature.com/nm.rss",
    "Cancer Cell": "https://www.cell.com/cancer-cell/rss/current",
    "Cell Systems": "https://www.cell.com/cell-systems/rss/current",
    "Genome Biology": "https://genomebiology.biomedcentral.com/articles/feed/",
    "Nucleic Acids Research": "https://academic.oup.com/rss/site_5127/3091.xml",
}


class RSSFeedSearcher:
    """Search papers using RSS feeds from major journals."""

    def __init__(self, custom_feeds: Optional[dict[str, str]] = None):
        """
        Initialize RSS feed searcher.

        Args:
            custom_feeds: Custom RSS feed URLs {journal_name: url}
        """
        self.feeds = {**JOURNAL_RSS_FEEDS}
        if custom_feeds:
            self.feeds.update(custom_feeds)

    def _parse_entry(self, entry: dict, journal: str) -> Optional[Paper]:
        """Parse a single RSS feed entry."""
        try:
            # Title
            title = entry.get("title", "").strip()
            if not title:
                return None

            # DOI
            doi = None
            if "doi" in entry:
                doi = entry["doi"]
            elif "dc_identifier" in entry:
                doi = entry["dc_identifier"]
            elif "prism_doi" in entry:
                doi = entry["prism_doi"]
            # Try to extract from link
            elif "link" in entry:
                link = entry["link"]
                if "doi.org/" in link:
                    doi = link.split("doi.org/")[-1]
                elif "/doi/" in link:
                    doi = link.split("/doi/")[-1].split("?")[0]

            # URL
            url = entry.get("link", "")

            # Publication date
            pub_date = None
            if "published_parsed" in entry and entry["published_parsed"]:
                pub_date = datetime.fromtimestamp(mktime(entry["published_parsed"]))
            elif "updated_parsed" in entry and entry["updated_parsed"]:
                pub_date = datetime.fromtimestamp(mktime(entry["updated_parsed"]))

            # Abstract/Summary
            abstract = ""
            if "summary" in entry:
                abstract = entry["summary"]
            elif "description" in entry:
                abstract = entry["description"]
            # Clean HTML tags
            abstract = self._strip_html(abstract)

            # Authors
            authors = []
            if "authors" in entry:
                for author in entry["authors"]:
                    if isinstance(author, dict):
                        authors.append(author.get("name", ""))
                    else:
                        authors.append(str(author))
            elif "author" in entry:
                authors = [entry["author"]]

            return Paper(
                title=title,
                doi=doi,
                authors=authors,
                journal=journal,
                publication_date=pub_date,
                abstract=abstract,
                url=url,
                source=PaperSource.RSS,
                is_open_access=False,  # Need to check separately
            )

        except Exception as e:
            print(f"Error parsing RSS entry: {e}")
            return None

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        import re
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    def _matches_keywords(self, paper: Paper, keywords: list[str]) -> bool:
        """Check if paper matches any of the keywords."""
        text = (paper.title + " " + paper.abstract).lower()
        return any(kw.lower() in text for kw in keywords)

    def search(
        self,
        keywords: list[str],
        journals: list[str],
        max_papers: int = 10,
        days_lookback: int = 7
    ) -> list[Paper]:
        """
        Search RSS feeds for papers.

        Args:
            keywords: Keywords to filter by
            journals: Journals to search
            max_papers: Maximum number of papers to return
            days_lookback: Number of days to look back

        Returns:
            List of Paper objects
        """
        papers = []
        cutoff_date = datetime.now() - timedelta(days=days_lookback)

        for journal in journals:
            feed_url = self.feeds.get(journal)
            if not feed_url:
                print(f"[RSS] No feed URL for journal: {journal}")
                continue

            print(f"[RSS] Fetching {journal} feed...")
            feed = feedparser.parse(feed_url)

            if feed.bozo:  # Feed parsing error
                print(f"[RSS] Error parsing {journal} feed: {feed.bozo_exception}")
                continue

            for entry in feed.entries:
                paper = self._parse_entry(entry, journal)
                if paper is None:
                    continue

                # Check date
                if paper.publication_date and paper.publication_date < cutoff_date:
                    continue

                # Check keywords
                if keywords and not self._matches_keywords(paper, keywords):
                    continue

                papers.append(paper)

        # Sort by date (newest first)
        papers.sort(key=lambda p: p.publication_date or datetime.min, reverse=True)

        print(f"[RSS] Found {len(papers)} papers matching criteria")
        return papers[:max_papers]
