"""Deduplication checker for papers."""

import re
import unicodedata

from ..models import Paper
from ..storage.history import PaperHistoryManager


def normalize_title(title: str) -> str:
    """Normalize a paper title for comparison.

    Strips punctuation, whitespace, accents, and lowercases
    so that minor formatting differences don't prevent dedup.
    """
    t = title.lower().strip()
    # Remove accents/diacritics
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    # Remove punctuation and extra whitespace
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


class DeduplicationChecker:
    """Check and filter duplicate papers."""

    def __init__(self, history_manager: PaperHistoryManager):
        """
        Initialize deduplication checker.

        Args:
            history_manager: Paper history manager instance
        """
        self.history = history_manager
        self._seen_in_session: set[str] = set()

    def _get_paper_keys(self, paper: Paper) -> list[str]:
        """Get all unique keys for a paper (DOI + normalized title).

        Returns multiple keys so a paper can be matched by either DOI or title.
        """
        keys = []
        if paper.doi:
            keys.append(f"doi:{paper.doi.lower().strip()}")
        if paper.pmid:
            keys.append(f"pmid:{paper.pmid.strip()}")
        # Always add normalized title as a fallback key
        keys.append(f"title:{normalize_title(paper.title)}")
        return keys

    def is_duplicate(self, paper: Paper) -> bool:
        """
        Check if paper is a duplicate.

        Checks both history and current session using all keys (DOI + title).

        Args:
            paper: Paper to check

        Returns:
            True if duplicate
        """
        keys = self._get_paper_keys(paper)

        # Check current session - match on ANY key
        for key in keys:
            if key in self._seen_in_session:
                return True

        # Check history
        return self.history.is_duplicate(paper)

    def mark_as_seen(self, paper: Paper) -> None:
        """Mark paper as seen in current session (registers all keys)."""
        for key in self._get_paper_keys(paper):
            self._seen_in_session.add(key)

    def filter_duplicates(self, papers: list[Paper]) -> list[Paper]:
        """
        Filter out duplicate papers.

        Args:
            papers: List of papers to filter

        Returns:
            List of unique, new papers
        """
        unique_papers = []

        for paper in papers:
            if not self.is_duplicate(paper):
                unique_papers.append(paper)
                self.mark_as_seen(paper)

        return unique_papers

    def save_to_history(self, papers: list[Paper]) -> None:
        """
        Save papers to history for future deduplication.

        Args:
            papers: Papers to save
        """
        self.history.add_papers(papers)

    def reset_session(self) -> None:
        """Reset session-level deduplication."""
        self._seen_in_session = set()
