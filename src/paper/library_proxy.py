"""Institutional library proxy (n2s / EZproxy-style) for fetching subscription PDFs.

Some institutions expose subscribed content via a URL-rewriting proxy such as
`libproxy.<institution>.kr:8443/link.n2s?url=<real_url>`. After a one-time
login the session cookie carries the subscription entitlement, and any request
to `link.n2s?url=<publisher_url>` gets rewritten to a `<host>-ssl.libproxy...`
domain where the publisher sees the proxy IP as authenticated.

IMPORTANT usage notes:
- This is meant for the researcher's own reading workflow, not for large-scale
  scraping. Publisher licenses typically forbid "automated / systematic
  downloading" and violations can get the entire institution's access revoked.
  Cron runs at most a handful of papers per week; keep it that way.
- Credentials live in .env (LIBPROXY_URL, LIBPROXY_ID, LIBPROXY_PASSWORD).
  Never commit them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
import urllib3

# Institutional proxies often use self-signed or otherwise non-standard SSL
# certificates. We disable verification for this session and silence urllib3
# warnings that would otherwise fire on every request.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LibraryProxyDownloader:
    """Log into an institutional n2s-style library proxy and download PDFs."""

    def __init__(self, proxy_base_url: str, user_id: str, password: str, timeout: int = 60):
        # proxy_base_url examples:
        #   https://libproxy.ncc.re.kr:8443
        #   https://libproxy.university.edu
        self.proxy_base = proxy_base_url.rstrip("/")
        self.user_id = user_id
        self.password = password
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._logged_in = False

    # -----------------------------------------------------------------
    # URL wrapping
    # -----------------------------------------------------------------
    def wrap(self, publisher_url: str) -> str:
        return f"{self.proxy_base}/link.n2s?url={publisher_url}"

    # -----------------------------------------------------------------
    # Login (mirrors the browser flow the proxy actually runs)
    # -----------------------------------------------------------------
    def login(self) -> bool:
        """Establish an authenticated session. Idempotent."""
        if self._logged_in:
            return True

        try:
            # Step 1: initial link.n2s → JS redirect page with authapi.n2s URL
            r1 = self.session.get(
                self.wrap("https://pubmed.ncbi.nlm.nih.gov/?otool=ikrncclib"),
                verify=False, timeout=self.timeout,
            )
            m = re.search(r'gourl = "([^"]+authapi\.n2s[^"]+)"', r1.text)
            if not m:
                print("[LibProxy] Login step 1 failed (no authapi URL)")
                return False
            auth_url = m.group(1).replace("&amp;", "&")

            # Step 2: authapi.n2s hands back a form auto-posting to ncc_ulogin.n2s
            r2 = self.session.get(auth_url, verify=False, timeout=self.timeout)
            m3 = re.search(r'name="returnurl" value="([^"]+)"', r2.text)
            if not m3:
                print("[LibProxy] Login step 2 failed (no returnurl)")
                return False
            returnurl = m3.group(1)

            # Step 3: POST credentials
            login_url = f"{self.proxy_base}/ncc_ulogin.n2s"
            r4 = self.session.post(
                login_url,
                data={
                    "returnurl": returnurl,
                    "confirm": "idpw",
                    "uid": self.user_id,
                    "upw": self.password,
                },
                verify=False, timeout=self.timeout,
            )
            if 'name="upw"' in r4.text:
                print("[LibProxy] Login failed (still on login form). Check LIBPROXY_ID/PASSWORD.")
                return False

            # Step 4: post-login page carries hmac_session_id — hitting the
            # constructed authapi URL is what actually stores the entitlement
            # cookie (_OpenlinkUID_) on this session.
            hmac_m = re.search(r'hmac_session_id="([^"]+)"', r4.text)
            ret_m = re.search(r'openlink_returnurl="([^"]+)"', r4.text)
            if not hmac_m or not ret_m:
                print("[LibProxy] Login step 4 failed (no hmac session)")
                return False
            final_auth = (
                f"{self.proxy_base}/authapi.n2s?u=login&apitype=direct"
                f"&hmac_session_id={hmac_m.group(1)}"
                f"&returnurl={quote(ret_m.group(1))}"
            )
            self.session.get(final_auth, verify=False, timeout=self.timeout)

            if not any(c.name == "_OpenlinkUID_" for c in self.session.cookies):
                print("[LibProxy] Login didn't produce _OpenlinkUID_ cookie")
                return False

            self._logged_in = True
            print(f"[LibProxy] Logged in as {self.user_id}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"[LibProxy] Login error: {e}")
            return False

    # -----------------------------------------------------------------
    # PDF download
    # -----------------------------------------------------------------
    def download_pdf(self, publisher_pdf_url: str, dest: Path) -> bool:
        """Fetch a PDF from a publisher URL via the authenticated proxy.

        Args:
            publisher_pdf_url: Direct PDF URL on the publisher site
                (e.g., https://www.science.org/doi/pdf/10.1126/sciadv.xyz)
            dest: Where to save the PDF
        """
        if not self.login():
            return False

        try:
            # Ask link.n2s for the JS-produced rewritten URL, then follow it
            r = self.session.get(
                self.wrap(publisher_pdf_url),
                verify=False, timeout=self.timeout,
            )
            rewritten = None
            m = re.search(r'gourl = "([^"]+)"', r.text)
            if m:
                rewritten = m.group(1)
            else:
                # Some link.n2s responses redirect via header directly; use as-is
                rewritten = r.url

            r2 = self.session.get(
                rewritten, verify=False, timeout=self.timeout, allow_redirects=True
            )
            ctype = r2.headers.get("content-type", "").lower()

            if r2.status_code != 200:
                print(f"[LibProxy] {publisher_pdf_url} -> HTTP {r2.status_code}")
                return False
            if "application/pdf" not in ctype and not r2.content.startswith(b"%PDF"):
                print(f"[LibProxy] Not a PDF (content-type={ctype[:40]})")
                return False

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r2.content)
            print(f"[LibProxy] Downloaded via proxy: {dest.name} ({len(r2.content) // 1024} KB)")
            return True
        except requests.exceptions.RequestException as e:
            print(f"[LibProxy] Download error: {e}")
            return False

    # -----------------------------------------------------------------
    # DOI helpers
    # -----------------------------------------------------------------
    @staticmethod
    def guess_pdf_url_from_doi(doi: str) -> Optional[str]:
        """Best-effort mapping from DOI to a publisher PDF URL.

        Not exhaustive — covers the publishers we hit most.
        """
        if not doi:
            return None
        d = doi.strip()
        if d.startswith("10.1038/"):  # Nature
            article_id = d.split("/", 1)[1]
            return f"https://www.nature.com/articles/{article_id}.pdf"
        if d.startswith("10.1126/"):  # Science / AAAS
            return f"https://www.science.org/doi/pdf/{d}?download=true"
        if d.startswith("10.1002/"):  # Wiley
            return f"https://onlinelibrary.wiley.com/doi/pdf/{d}"
        if d.startswith("10.1093/"):  # Oxford (NAR, Bioinformatics)
            return f"https://academic.oup.com/{d}"
        # Cell Press, Elsevier: PDF path isn't easily derivable from DOI alone.
        # Fall back to the DOI resolver so the publisher decides where to send us.
        return f"https://doi.org/{d}"
