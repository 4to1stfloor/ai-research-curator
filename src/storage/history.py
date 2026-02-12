"""Paper history management for deduplication."""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Paper, PaperHistoryEntry


class PaperHistoryManager:
    """Manage paper history for deduplication."""

    def __init__(self, history_file: str | Path):
        """
        Initialize history manager.

        Args:
            history_file: Path to the history JSON file
        """
        self.history_file = Path(history_file)
        self._entries: list[PaperHistoryEntry] = []
        self._doi_set: set[str] = set()
        self._title_set: set[str] = set()
        self._load()

    def _load(self) -> None:
        """Load history from file."""
        if not self.history_file.exists():
            self._save()
            return

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._entries = [
                PaperHistoryEntry.from_dict(entry)
                for entry in data.get("papers", [])
            ]

            # Build lookup sets
            for entry in self._entries:
                if entry.doi:
                    self._doi_set.add(entry.doi.lower())
                self._title_set.add(self._normalize_title(entry.title))

        except Exception as e:
            print(f"Error loading history: {e}")
            self._entries = []

    def _save(self) -> None:
        """Save history to file."""
        # Ensure directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "papers": [entry.to_dict() for entry in self._entries],
            "last_updated": datetime.now().isoformat()
        }

        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison.

        Strips punctuation, whitespace, accents, and lowercases
        so minor formatting differences don't prevent dedup.
        """
        t = title.lower().strip()
        t = unicodedata.normalize('NFKD', t)
        t = ''.join(c for c in t if not unicodedata.combining(c))
        t = re.sub(r'[^\w\s]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def is_duplicate(self, paper: Paper) -> bool:
        """
        Check if a paper is already in history.

        Args:
            paper: Paper to check

        Returns:
            True if paper is a duplicate
        """
        # Check by DOI (most reliable)
        if paper.doi and paper.doi.lower() in self._doi_set:
            return True

        # Check by title (fallback)
        normalized_title = self._normalize_title(paper.title)
        if normalized_title in self._title_set:
            return True

        return False

    def add_paper(self, paper: Paper) -> None:
        """
        Add a paper to history.

        Args:
            paper: Paper to add
        """
        if self.is_duplicate(paper):
            return

        entry = PaperHistoryEntry(
            doi=paper.doi,
            title=paper.title,
            added_date=datetime.now()
        )

        self._entries.append(entry)

        # Update lookup sets
        if paper.doi:
            self._doi_set.add(paper.doi.lower())
        self._title_set.add(self._normalize_title(paper.title))

        self._save()

    def add_papers(self, papers: list[Paper]) -> None:
        """
        Add multiple papers to history.

        Args:
            papers: List of papers to add
        """
        for paper in papers:
            if not self.is_duplicate(paper):
                entry = PaperHistoryEntry(
                    doi=paper.doi,
                    title=paper.title,
                    added_date=datetime.now()
                )
                self._entries.append(entry)

                if paper.doi:
                    self._doi_set.add(paper.doi.lower())
                self._title_set.add(self._normalize_title(paper.title))

        self._save()

    def filter_new_papers(self, papers: list[Paper]) -> list[Paper]:
        """
        Filter out papers that are already in history.

        Args:
            papers: List of papers to filter

        Returns:
            List of papers not in history
        """
        return [p for p in papers if not self.is_duplicate(p)]

    def get_history_count(self) -> int:
        """Get number of papers in history."""
        return len(self._entries)

    def get_recent_entries(self, days: int = 30) -> list[PaperHistoryEntry]:
        """
        Get entries from the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of recent entries
        """
        cutoff = datetime.now() - timedelta(days=days)
        return [e for e in self._entries if e.added_date >= cutoff]

    def clear_history(self) -> None:
        """Clear all history."""
        self._entries = []
        self._doi_set = set()
        self._title_set = set()
        self._save()


# Need to import timedelta
from datetime import timedelta
