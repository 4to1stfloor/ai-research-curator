"""RSS feed parser for journal papers."""

import re
from datetime import datetime, timedelta
from typing import Optional
from time import mktime

import feedparser
import requests

from ..models import Paper, PaperSource

# Journal RSS feeds - with alternatives for problematic feeds
JOURNAL_RSS_FEEDS = {
    # Nature journals (reliable)
    "Nature": "https://www.nature.com/nature.rss",
    "Nature Methods": "https://www.nature.com/nmeth.rss",
    "Nature Biotechnology": "https://www.nature.com/nbt.rss",
    "Nature Medicine": "https://www.nature.com/nm.rss",
    "Nature Communications": "https://www.nature.com/ncomms.rss",
    "Nature Genetics": "https://www.nature.com/ng.rss",
    "Nature Cell Biology": "https://www.nature.com/ncb.rss",

    # Science journals
    "Science": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    "Science Advances": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",

    # Cell journals - use Atom feed as alternative (more reliable)
    "Cell": "https://www.cell.com/cell/current.rss",
    "Cancer Cell": "https://www.cell.com/cancer-cell/current.rss",
    "Cell Systems": "https://www.cell.com/cell-systems/current.rss",
    "Cell Stem Cell": "https://www.cell.com/cell-stem-cell/current.rss",
    "Molecular Cell": "https://www.cell.com/molecular-cell/current.rss",

    # BMC journals. Springer currently serves a bot-check HTML page instead
    # of these feeds (2026-10-14); _fetch_feed detects that and these journals
    # are then covered by the PubMed search alone.
    "Genome Biology": "https://genomebiology.biomedcentral.com/articles/most-recent/rss.xml",
    "BMC Genomics": "https://bmcgenomics.biomedcentral.com/articles/most-recent/rss.xml",
    "BMC Bioinformatics": "https://bmcbioinformatics.biomedcentral.com/articles/most-recent/rss.xml",

    # Oxford journals. The old /<journal>/rss/advanceAccess paths 404 since
    # OUP moved feeds to /rss/site_<id>/... (found 2026-10-14). Advance Access
    # carries new papers first; the current-issue feed catches the rest.
    "Nucleic Acids Research": [
        "https://academic.oup.com/rss/site_5127/advanceAccess_3091.xml",
        "https://academic.oup.com/rss/site_5127/3091.xml",
    ],
    "Bioinformatics": [
        "https://academic.oup.com/rss/site_5139/advanceAccess_3001.xml",
        "https://academic.oup.com/rss/site_5139/3001.xml",
    ],

    # PLOS journals (always open access)
    "PLOS Biology": "https://journals.plos.org/plosbiology/feed/atom",
    "PLOS Genetics": "https://journals.plos.org/plosgenetics/feed/atom",
    "PLOS Computational Biology": "https://journals.plos.org/ploscompbiol/feed/atom",

    # eLife (open access)
    "eLife": "https://elifesciences.org/rss/recent.xml",
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
            # Try to extract from link / Atom id. PLOS links look like
            # .../article?id=10.1371/journal.pbio.3003xxx, which the old
            # "doi.org/" / "/doi/" checks missed, leaving PLOS papers without
            # a DOI (no dedup against PubMed, no DOI-based fetching).
            if not doi:
                for src in (entry.get("link", ""), entry.get("id", "")):
                    m = re.search(r'(10\.\d{4,9}/[^\s?&#"<>]+)', src or "")
                    if m:
                        doi = m.group(1).rstrip("/.")
                        break
            if doi:
                doi = re.sub(r'^(?:doi:|https?://(?:dx\.)?doi\.org/)', '', doi.strip(), flags=re.I)

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
            # Clean HTML tags and RSS metadata
            abstract = self._drop_leading_byline(abstract)
            abstract = self._strip_html(abstract)
            abstract = self._clean_abstract(abstract, journal)

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

            # Determine if journal is Open Access
            open_access_journals = {
                "Nature Communications",
                "PLOS Biology", "PLOS Genetics", "PLOS Computational Biology",
                "eLife",
                "Genome Biology", "BMC Genomics", "BMC Bioinformatics",
                "Science Advances",  # Most articles are open access
            }
            is_open_access = journal in open_access_journals

            # Determine article type from title or category
            article_type = "Research Article"  # default
            non_research_keywords = [
                "Perspective", "Review", "Editorial", "Commentary",
                "Opinion", "Letter", "Correspondence", "Erratum",
                "Correction", "Retraction", "News", "Primer", "Viewpoint"
            ]

            # Check title for article type indicators
            title_lower = title.lower()
            for keyword in non_research_keywords:
                if keyword.lower() in title_lower:
                    article_type = keyword
                    break

            # Also check RSS category/tags if available
            categories = entry.get("tags", []) or entry.get("categories", [])
            for cat in categories:
                cat_term = cat.get("term", "") if isinstance(cat, dict) else str(cat)
                for keyword in non_research_keywords:
                    if keyword.lower() in cat_term.lower():
                        article_type = keyword
                        break

            return Paper(
                title=title,
                doi=doi,
                authors=authors,
                journal=journal,
                publication_date=pub_date,
                abstract=abstract,
                url=url,
                source=PaperSource.RSS,
                is_open_access=is_open_access,
                article_type=article_type,
            )

        except Exception as e:
            print(f"Error parsing RSS entry: {e}")
            return None

    @staticmethod
    def _drop_leading_byline(raw: str) -> str:
        """Remove the author byline PLOS feeds put before the abstract.

        PLOS Atom summaries open with "<p>by Author A, Author B</p>" and then
        the abstract. It has to go before the tags are stripped: _strip_html
        collapses whitespace, after which there is no way to tell where the
        author list ends and the abstract begins. Left in, it became the first
        "sentence" of the abstract and got translated as "저자: ...".
        """
        import re
        return re.sub(r'^\s*<p>\s*by\s+.*?</p>', '', raw or '',
                      count=1, flags=re.DOTALL | re.IGNORECASE)

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        import re
        # Block-level tags become spaces so "<h2>Abstract</h2><p>Text" does
        # not fuse into "AbstractText" (OUP feeds); inline tags vanish.
        clean = re.sub(r'</?(?:p|div|h[1-6]|br|li|ul|ol|section|span class="[^"]*title[^"]*")[^>]*>', ' ', text, flags=re.I)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    def _clean_abstract(self, abstract: str, journal: str) -> str:
        """Clean abstract by removing RSS metadata."""
        import re

        # Remove common RSS metadata patterns
        # Pattern: "Journal Name, Published online: DD Month YYYY; doi:..."
        abstract = re.sub(
            r'^[A-Za-z\s]+,\s*Published\s+online:\s*\d+\s+\w+\s+\d+;\s*doi:[^\s]+',
            '',
            abstract
        )

        # Pattern: "Nature Biotechnology, doi:10.1038/..."
        abstract = re.sub(
            r'^[A-Za-z\s]+,\s*doi:\d+\.\d+/[^\s]+',
            '',
            abstract
        )

        # Pattern: Leading journal name
        if journal and abstract.lower().startswith(journal.lower()):
            abstract = abstract[len(journal):].lstrip(',').lstrip()

        # Pattern: "doi:10.xxxx/..." at the start
        abstract = re.sub(r'^doi:\S+\s*', '', abstract)

        # Science/Science Advances feeds put only "Volume 12, Issue 41,
        # October 2026." in the description. That is not an abstract; leave it
        # empty so the processing step fetches the real one.
        if re.fullmatch(r'\s*Volume\s+\d+,\s*Issue\s+\d+,?[^.]{0,30}\.?\s*', abstract or ''):
            return ""

        # Leading "Abstract" heading (OUP), plus Bioinformatics' first
        # structured-abstract label ("Motivation"/"Summary").
        abstract = re.sub(r'^\s*Abstract\b[:.]?\s*', '', abstract, flags=re.I)
        abstract = re.sub(r'^\s*(?:Motivation|Summary)\s+(?=[A-Z])', '', abstract)

        return abstract.strip()

    def _matches_keywords(self, paper: Paper, keywords: list[str]) -> bool:
        """Check if paper matches any of the keywords."""
        text = (paper.title + " " + paper.abstract).lower()
        return any(kw.lower() in text for kw in keywords)

    def _fetch_feed(self, url: str, journal: str) -> Optional[feedparser.FeedParserDict]:
        """Fetch RSS feed with custom headers and error handling."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

        try:
            # First try with requests to get content with proper encoding
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # A bot wall answers 200 with an HTML page, which feedparser
            # "parses" into zero entries plus a vague bozo warning. Say so.
            ctype = response.headers.get("content-type", "").lower()
            head = response.content[:200].lstrip().lower()
            if "html" in ctype or head.startswith(b"<!doctype html") or head.startswith(b"<html"):
                print(f"[RSS] {journal}: site returned a web page (bot check) instead of RSS "
                      f"- this journal is covered by the PubMed search only")
                return None

            # Parse the content directly
            feed = feedparser.parse(response.content)
            return feed

        except requests.RequestException as e:
            print(f"[RSS] HTTP error for {journal}: {e}")
            # Fallback to feedparser direct fetch
            try:
                feed = feedparser.parse(url)
                if not feed.bozo:
                    return feed
            except Exception:
                pass

        return None

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
        successful_feeds = 0
        failed_feeds = 0

        for journal in journals:
            feed_url = self.feeds.get(journal)
            if not feed_url:
                # Check for partial matches (e.g., "Nature" matches "Nature Methods")
                for j_name, j_url in self.feeds.items():
                    if journal.lower() in j_name.lower() or j_name.lower() in journal.lower():
                        feed_url = j_url
                        journal = j_name
                        break

            if not feed_url:
                continue

            print(f"[RSS] Fetching {journal} feed...")
            urls = feed_url if isinstance(feed_url, list) else [feed_url]
            entries = []
            for u in urls:
                feed = self._fetch_feed(u, journal)
                if feed is None:
                    continue
                if feed.bozo and not feed.entries:
                    print(f"[RSS] {journal}: feed could not be parsed ({feed.get('bozo_exception')!r:.80})")
                    continue
                entries.extend(feed.entries)

            if not entries:
                print(f"[RSS] Failed to fetch {journal} feed")
                failed_feeds += 1
                continue

            entry_count = 0
            for entry in entries:
                paper = self._parse_entry(entry, journal)
                if paper is None:
                    continue

                # Check date (if available)
                if paper.publication_date:
                    if paper.publication_date < cutoff_date:
                        continue
                # If no date, include the paper (RSS feeds usually show recent papers)

                # Check keywords
                if keywords and not self._matches_keywords(paper, keywords):
                    continue

                papers.append(paper)
                entry_count += 1

            if entry_count > 0:
                successful_feeds += 1
                print(f"[RSS] Found {entry_count} matching papers from {journal}")

        # Sort by date (newest first)
        papers.sort(key=lambda p: p.publication_date or datetime.min, reverse=True)

        # Remove duplicates by DOI or title
        seen = set()
        unique_papers = []
        for p in papers:
            key = p.doi or p.title.lower()
            if key not in seen:
                seen.add(key)
                unique_papers.append(p)

        print(f"[RSS] Total: {len(unique_papers)} unique papers from {successful_feeds} feeds ({failed_feeds} failed)")
        return unique_papers[:max_papers]
