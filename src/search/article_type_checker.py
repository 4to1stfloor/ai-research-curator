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
# Values are normalized (lowercase, alpha-only) before matching.
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
    "reviewpaper",         # Nature's actual dc.type for review articles
    "reviewarticle",
    "systematicreview",
    "metaanalysis",
    "viewpoint",
    "opinion",
    "correspondence",
    "matterarising",
    "retraction",
    "correction",
    "erratum",
    "highlight",
    "protocol",  # Nature Protocols entries — methods/recipes, not new findings
    "addendum",
    "publishererratum",
    "case-report",
    "casereport",
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


# ---------------------------------------------------------------------------
# Generic checks that work for publishers without a dc.type tag (Cell Press,
# Elsevier, AACR, ...). Cell Press "Preview" pieces are labeled plain
# "Journal Article" by both PubMed and Crossref (2026-10-14: a 3-page Cancer
# Cell Preview went into the report as paper #3), so we look at what the
# article physically is: its page span, and the type label printed at the top
# of its first PDF page.
# ---------------------------------------------------------------------------

# Labels publishers print as the first line of a non-research PDF.
PDF_NON_RESEARCH_LABELS = {
    "preview", "previews", "commentary", "perspective", "perspectives",
    "review", "minireview", "editorial", "correspondence", "mattersarising",
    "voices", "spotlight", "forum", "essay", "qa", "qanda", "primer",
    "newsandviews", "newsviews", "comment", "viewpoint", "opinion",
    "highlight", "researchhighlight", "erratum", "correction", "retraction",
    "leadingedge", "snapshot", "outlook", "focus",
}

# Short-format research types we must NOT exclude even though they are short.
PDF_RESEARCH_LABELS = {
    "article", "researcharticle", "report", "shortarticle", "letter",
    "resource", "clinicalandtranslationalreport", "brief report",
}

MAX_NON_RESEARCH_PAGES = 3


def crossref_page_count(doi: str, mailto: Optional[str] = None) -> Optional[int]:
    """Page span from Crossref ("1921-1923" -> 3), or None if unknown.

    Article-number style journals (PLOS e1014041, eLife, NAR gkag964) have no
    page range and return None, so they are never affected.
    """
    if not doi:
        return None
    import requests
    doi = re.sub(r"^doi:\s*", "", doi.strip(), flags=re.IGNORECASE)
    try:
        params = {"mailto": mailto} if mailto else None
        r = requests.get(f"https://api.crossref.org/works/{doi}", params=params, timeout=15)
        if r.status_code != 200:
            return None
        page = (r.json().get("message") or {}).get("page") or ""
    except Exception:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", page)
    if not m:
        return None
    first, last = int(m.group(1)), int(m.group(2))
    if last < first:
        return None
    return last - first + 1


def pdf_article_type_label(pdf_path: str) -> Optional[str]:
    """Return the non-research label printed atop page 1, or None.

    Cell Press / Elsevier PDFs start with the article type on its own line
    ("Preview", "Commentary", "Review"...). Only the first few short lines are
    checked so a word in the title or abstract cannot trigger it.
    """
    try:
        import fitz
        with fitz.open(pdf_path) as doc:
            if len(doc) == 0:
                return None
            text = doc[0].get_text()
    except Exception:
        return None
    for line in text.splitlines()[:4]:
        line = line.strip()
        if not line or len(line) > 40:
            continue
        norm = _normalize(line)
        if norm in PDF_RESEARCH_LABELS:
            return None
        if norm in PDF_NON_RESEARCH_LABELS:
            return line
    return None
