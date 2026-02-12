"""PubMed E-utilities API searcher."""

import time
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Paper, PaperSource

# PubMed E-utilities base URLs
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedSearcher:
    """Search papers using PubMed E-utilities API."""

    def __init__(self, email: Optional[str] = None):
        """
        Initialize PubMed searcher.

        Args:
            email: Email for NCBI API (recommended for higher rate limits)
        """
        self.email = email
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AutoPaperScraper/1.0"
        })

    def _build_query(
        self,
        keywords: list[str],
        journals: list[str],
        days_lookback: int
    ) -> str:
        """Build PubMed search query."""
        # Keyword part (OR)
        keyword_query = " OR ".join([f'("{kw}"[Title/Abstract])' for kw in keywords])

        # Journal part (OR)
        journal_query = " OR ".join([f'("{j}"[Journal])' for j in journals])

        # Date part
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_lookback)
        date_query = f'{start_date.strftime("%Y/%m/%d")}:{end_date.strftime("%Y/%m/%d")}[Date - Publication]'

        # Combine: (keywords) AND (journals) AND date
        query = f"({keyword_query}) AND ({journal_query}) AND ({date_query})"

        return query

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _esearch(self, query: str, max_results: int = 100) -> list[str]:
        """
        Search PubMed and return PMIDs.

        Args:
            query: PubMed search query
            max_results: Maximum number of results

        Returns:
            List of PMIDs
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "xml",
            "sort": "date",
        }
        if self.email:
            params["email"] = self.email

        response = self.session.get(ESEARCH_URL, params=params)
        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.content)
        pmids = [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]

        return pmids

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _efetch(self, pmids: list[str]) -> list[Paper]:
        """
        Fetch paper details from PubMed.

        Args:
            pmids: List of PMIDs to fetch

        Returns:
            List of Paper objects
        """
        if not pmids:
            return []

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if self.email:
            params["email"] = self.email

        response = self.session.get(EFETCH_URL, params=params)
        response.raise_for_status()

        # Parse XML response
        papers = []
        root = ET.fromstring(response.content)

        for article in root.findall(".//PubmedArticle"):
            paper = self._parse_article(article)
            if paper:
                papers.append(paper)

        return papers

    def _parse_article(self, article: ET.Element) -> Optional[Paper]:
        """Parse a single PubMed article XML element."""
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None

            # PMID
            pmid_elem = medline.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None

            # Article info
            article_elem = medline.find(".//Article")
            if article_elem is None:
                return None

            # Title - use itertext() to capture text across sub/sup tags
            title_elem = article_elem.find(".//ArticleTitle")
            title = "".join(title_elem.itertext()) if title_elem is not None else ""

            # Abstract - use itertext() to capture text across sub/sup tags
            abstract_parts = []
            for abstract_text in article_elem.findall(".//AbstractText"):
                label = abstract_text.get("Label", "")
                text = "".join(abstract_text.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            # Authors
            authors = []
            for author in article_elem.findall(".//Author"):
                last_name = author.find("LastName")
                fore_name = author.find("ForeName")
                if last_name is not None and fore_name is not None:
                    authors.append(f"{fore_name.text} {last_name.text}")
                elif last_name is not None:
                    authors.append(last_name.text)

            # Journal
            journal_elem = article_elem.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""

            # Publication date
            pub_date = None
            pub_date_elem = article_elem.find(".//PubDate")
            if pub_date_elem is not None:
                year = pub_date_elem.find("Year")
                month = pub_date_elem.find("Month")
                day = pub_date_elem.find("Day")
                if year is not None:
                    try:
                        year_val = int(year.text)
                        month_val = self._parse_month(month.text) if month is not None else 1
                        day_val = int(day.text) if day is not None else 1
                        pub_date = datetime(year_val, month_val, day_val)
                    except (ValueError, TypeError):
                        pass

            # DOI
            doi = None
            for eloc in article_elem.findall(".//ELocationID"):
                if eloc.get("EIdType") == "doi":
                    doi = eloc.text
                    break

            # PMCID and Open Access
            pmcid = None
            is_open_access = False
            pmc_elem = article.find(".//PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
            if pmc_elem is not None:
                pmcid = pmc_elem.text
                is_open_access = True

            # URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            # PDF URL (for PMC articles)
            pdf_url = None
            if pmcid:
                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"

            # Keywords
            keywords = []
            for kw in medline.findall(".//KeywordList/Keyword"):
                if kw.text:
                    keywords.append(kw.text)

            # Publication types
            pub_types = []
            for pt in article_elem.findall(".//PublicationTypeList/PublicationType"):
                if pt.text:
                    pub_types.append(pt.text)

            # Determine article type
            article_type = "Research Article"  # default
            non_research_types = [
                "Review", "Editorial", "Comment", "Letter", "News",
                "Published Erratum", "Retracted Publication", "Biography",
                "Historical Article", "Interview", "Lecture", "Guideline"
            ]
            for pt in pub_types:
                if any(nrt.lower() in pt.lower() for nrt in non_research_types):
                    article_type = pt
                    break

            # Also check abstract for Perspective/Review indicators
            if article_type == "Research Article" and abstract:
                abstract_lower = abstract.lower()
                perspective_indicators = [
                    "this perspective", "in this perspective",
                    "this review", "in this review",
                    "this commentary", "in this commentary",
                    "this opinion", "this viewpoint"
                ]
                for indicator in perspective_indicators:
                    if indicator in abstract_lower:
                        article_type = "Perspective"
                        break

            return Paper(
                title=title,
                doi=doi,
                pmid=pmid,
                pmcid=pmcid,
                authors=authors,
                journal=journal,
                publication_date=pub_date,
                abstract=abstract,
                keywords=keywords,
                url=url,
                pdf_url=pdf_url,
                source=PaperSource.PUBMED,
                is_open_access=is_open_access,
                article_type=article_type,
            )

        except Exception as e:
            print(f"Error parsing article: {e}")
            return None

    def _parse_month(self, month_str: str) -> int:
        """Parse month string to integer."""
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        try:
            return int(month_str)
        except ValueError:
            return month_map.get(month_str.lower()[:3], 1)

    def search(
        self,
        keywords: list[str],
        journals: list[str],
        max_papers: int = 10,
        days_lookback: int = 7
    ) -> list[Paper]:
        """
        Search PubMed for papers.

        Args:
            keywords: Keywords to search for
            journals: Journals to search in
            max_papers: Maximum number of papers to return
            days_lookback: Number of days to look back

        Returns:
            List of Paper objects
        """
        query = self._build_query(keywords, journals, days_lookback)
        print(f"[PubMed] Searching with query: {query[:100]}...")

        # Search for PMIDs
        pmids = self._esearch(query, max_results=max_papers * 2)  # Get extra in case of duplicates
        print(f"[PubMed] Found {len(pmids)} PMIDs")

        if not pmids:
            return []

        # Rate limiting
        time.sleep(0.5)

        # Fetch details
        papers = self._efetch(pmids[:max_papers])
        print(f"[PubMed] Retrieved {len(papers)} papers")

        return papers
