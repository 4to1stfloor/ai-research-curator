"""Data models for the paper scraping system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class PaperSource(Enum):
    """Source of the paper."""
    PUBMED = "pubmed"
    RSS = "rss"
    BIORXIV = "biorxiv"


@dataclass
class Paper:
    """Represents a research paper."""

    # Required fields
    title: str
    doi: Optional[str]

    # Identifiers
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    biorxiv_id: Optional[str] = None

    # Metadata
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    publication_date: Optional[datetime] = None

    # Content
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)

    # URLs
    url: str = ""
    pdf_url: Optional[str] = None

    # Source tracking
    source: PaperSource = PaperSource.PUBMED

    # Processing flags
    is_open_access: bool = False

    # Local paths (after download)
    local_pdf_path: Optional[str] = None
    extracted_figures: list[str] = field(default_factory=list)

    def __hash__(self):
        """Hash based on DOI or title."""
        return hash(self.doi or self.title)

    def __eq__(self, other):
        """Compare papers by DOI or title."""
        if not isinstance(other, Paper):
            return False
        if self.doi and other.doi:
            return self.doi == other.doi
        return self.title.lower() == other.title.lower()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "biorxiv_id": self.biorxiv_id,
            "authors": self.authors,
            "journal": self.journal,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "source": self.source.value,
            "is_open_access": self.is_open_access,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Paper":
        """Create Paper from dictionary."""
        pub_date = None
        if data.get("publication_date"):
            try:
                pub_date = datetime.fromisoformat(data["publication_date"])
            except (ValueError, TypeError):
                pass

        return cls(
            title=data.get("title", ""),
            doi=data.get("doi"),
            pmid=data.get("pmid"),
            pmcid=data.get("pmcid"),
            biorxiv_id=data.get("biorxiv_id"),
            authors=data.get("authors", []),
            journal=data.get("journal", ""),
            publication_date=pub_date,
            abstract=data.get("abstract", ""),
            keywords=data.get("keywords", []),
            url=data.get("url", ""),
            pdf_url=data.get("pdf_url"),
            source=PaperSource(data.get("source", "pubmed")),
            is_open_access=data.get("is_open_access", False),
        )


@dataclass
class ProcessedPaper:
    """Paper with AI-processed content."""

    paper: Paper

    # AI-generated content
    summary_korean: str = ""
    abstract_translation: list[dict] = field(default_factory=list)  # [{"en": ..., "ko": ...}, ...]
    summary_image_path: Optional[str] = None

    # Extracted content
    figures: list[str] = field(default_factory=list)  # paths to extracted figures

    # Processing metadata
    processed_at: datetime = field(default_factory=datetime.now)
    llm_provider: str = ""


@dataclass
class PaperHistoryEntry:
    """Entry in paper history for deduplication."""

    doi: Optional[str]
    title: str
    added_date: datetime

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "added_date": self.added_date.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperHistoryEntry":
        return cls(
            doi=data.get("doi"),
            title=data.get("title", ""),
            added_date=datetime.fromisoformat(data["added_date"])
        )
