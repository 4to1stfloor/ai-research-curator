"""Deduplication checker for papers."""

from ..models import Paper
from ..storage.history import PaperHistoryManager


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

    def _get_paper_key(self, paper: Paper) -> str:
        """Get unique key for paper."""
        if paper.doi:
            return f"doi:{paper.doi.lower()}"
        return f"title:{paper.title.lower().strip()}"

    def is_duplicate(self, paper: Paper) -> bool:
        """
        Check if paper is a duplicate.

        Checks both history and current session.

        Args:
            paper: Paper to check

        Returns:
            True if duplicate
        """
        key = self._get_paper_key(paper)

        # Check current session
        if key in self._seen_in_session:
            return True

        # Check history
        return self.history.is_duplicate(paper)

    def mark_as_seen(self, paper: Paper) -> None:
        """Mark paper as seen in current session."""
        key = self._get_paper_key(paper)
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
