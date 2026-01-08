"""Paper processing modules."""

from .downloader import PaperDownloader
from .parser import PDFParser
from .deduplication import DeduplicationChecker

__all__ = ["PaperDownloader", "PDFParser", "DeduplicationChecker"]
