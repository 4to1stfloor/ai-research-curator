"""Detect publisher-specific article types that PubMed/RSS doesn't expose properly.

Nature classifies papers as Article/Letter/Comment/Resource/News/etc. via
`<meta name="dc.type">` in the article HTML. PubMed often labels all of these
as "Journal Article", so we need to fetch the page to identify non-research
types like Comment, Brief Communication, Research Highlight, etc.
"""

import re
import subprocess
from typing import Optional


# Nature dc.type values that count as research papers (keep)
NATURE_RESEARCH_TYPES = {
    "article",
    "letter",
    "researcharticle",
    "researcharticletype",
}

# Nature dc.type values that are NOT research papers (exclude)
NATURE_NON_RESEARCH_TYPES = {
    "briefcommunication",
    "comment",
    "commentary",
    "editorial",
    "news",
    "newsandviews",
    "outlook",
    "perspective",
    "qanda",
    "researchhighlight",
    "resource",  # data/tool descriptions, not primary research
    "review",
    "viewpoint",
    "opinion",
    "correspondence",
    "matter arising",
    "matterarising",
    "retraction",
    "correction",
    "erratum",
    "highlight",
}


def _is_nature_doi(doi: str) -> bool:
    return doi and "10.1038/" in doi


def _is_cell_doi(doi: str) -> bool:
    return doi and "10.1016/j.cell" in doi


def _normalize(value: str) -> str:
    """Lowercase + strip whitespace + remove non-alnum for matching."""
    return re.sub(r"[^a-z]", "", (value or "").lower())


def _fetch_html(url: str, timeout: int = 20) -> Optional[str]:
    """Fetch HTML via curl (more robust against Cloudflare than requests)."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-L",
                "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "-H", "Accept: text/html",
                url,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and len(result.stdout) > 500:
            return result.stdout
    except Exception:
        pass
    return None


def detect_publisher_article_type(doi: str, url: Optional[str] = None) -> Optional[str]:
    """Try to detect article type from publisher metadata.

    Returns a normalized label (e.g., "Comment", "Brief Communication", "Article")
    or None if we couldn't determine it.
    """
    if not doi:
        return None

    # Only handle Nature for now (most common case in our journal list)
    if not _is_nature_doi(doi):
        return None

    target_url = url or f"https://doi.org/{doi}"
    html = _fetch_html(target_url)
    if not html:
        return None

    # Look for <meta name="dc.type" content="...">
    match = re.search(
        r'<meta\s+name=["\']dc\.type["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if not match:
        return None

    raw_type = match.group(1).strip()
    return raw_type


def is_non_research_type(publisher_type: str) -> bool:
    """Return True if the publisher's article type is NOT a research article."""
    if not publisher_type:
        return False
    norm = _normalize(publisher_type)
    if norm in NATURE_RESEARCH_TYPES:
        return False
    return norm in NATURE_NON_RESEARCH_TYPES
