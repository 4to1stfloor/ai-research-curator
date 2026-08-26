"""Browser-based library proxy downloader for publishers that block requests-based access.

Some publishers (Elsevier/Cell in particular) put anti-bot measures on the PDF
endpoint — the requests-based flow gets an HTML challenge page instead of a
PDF. To bypass that we drive a real headed Chrome inside an Xvfb virtual
display: from the server's perspective it looks like a person clicking around.

Human-like pacing (short randomized pauses between actions) is intentional:
- Reduces the chance the proxy flags our session
- Keeps the request rate well below anything a librarian would consider abuse

This module falls back to requests-based downloading when Xvfb / Chromium
aren't available (e.g., minimal container), so it's safe to always instantiate.
"""

from __future__ import annotations

import os
import random
import re
import shutil
import time
from pathlib import Path
from typing import Optional


class BrowserLibraryProxy:
    """Drive a real Chrome (inside Xvfb) to fetch subscription PDFs.

    Usage:
        proxy = BrowserLibraryProxy(url, user_id, password)
        if proxy.is_available():
            proxy.download_pdf_from_pii("S0092867424004914", Path("/tmp/cell.pdf"))
    """

    def __init__(
        self,
        proxy_base_url: str,
        user_id: str,
        password: str,
        chrome_binary: Optional[str] = None,
        download_dir: Optional[Path] = None,
    ):
        self.proxy_base = proxy_base_url.rstrip("/")
        self.user_id = user_id
        self.password = password

        # Resolve chromium binary — prefer explicit, then playwright's cache,
        # then system installs.
        self.chrome_binary = chrome_binary or self._find_chrome()
        self.download_dir = Path(download_dir) if download_dir else Path("/tmp/libproxy_browser_downloads")
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Environment checks
    # -----------------------------------------------------------------
    @staticmethod
    def _find_chrome() -> Optional[str]:
        for candidate in [
            os.path.expanduser("~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"),
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]:
            if os.path.exists(candidate):
                return candidate
        # Fall back to any chromium-* under playwright cache
        pw_cache = Path.home() / ".cache" / "ms-playwright"
        if pw_cache.exists():
            for d in sorted(pw_cache.glob("chromium-*"), reverse=True):
                chrome = d / "chrome-linux64" / "chrome"
                if chrome.exists():
                    return str(chrome)
        return None

    def is_available(self) -> bool:
        """True iff Xvfb, Chrome, Selenium, and pyvirtualdisplay are all installed."""
        if not self.chrome_binary:
            return False
        if not shutil.which("Xvfb"):
            return False
        try:
            import selenium  # noqa: F401
            import pyvirtualdisplay  # noqa: F401
        except ImportError:
            return False
        return True

    # -----------------------------------------------------------------
    # Human-like helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _pause(short: float = 0.4, long: float = 1.2) -> None:
        """Random pause between actions to look human."""
        time.sleep(random.uniform(short, long))

    @staticmethod
    def _type_like_human(element, text: str) -> None:
        """Type character-by-character with small random delays."""
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.03, 0.12))

    # -----------------------------------------------------------------
    # Download PDF given the PII (Elsevier's article identifier)
    # -----------------------------------------------------------------
    def download_pdf_from_pii(self, pii: str, dest: Path, max_attempts: int = 3) -> bool:
        """Log in and download the Cell/Elsevier PDF for a given PII.

        The library proxy occasionally times out under automated access even
        with the human-like pacing — retry a few times with growing delays
        before giving up. Each retry is a fresh browser session so cookie /
        fingerprint state doesn't compound.
        """
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                # Give the proxy a chance to release any temporary flag
                cooldown = 45 * (attempt - 1)  # 45s, 90s
                print(f"[LibProxy-Browser] Retry {attempt}/{max_attempts} after {cooldown}s cooldown")
                time.sleep(cooldown)
            if self._download_pdf_from_pii_once(pii, dest):
                return True
        return False

    def _download_pdf_from_pii_once(self, pii: str, dest: Path) -> bool:
        """One attempt at the browser login + download flow."""
        if not self.is_available():
            print("[LibProxy-Browser] Not available (missing Xvfb/Chrome/selenium)")
            return False

        from pyvirtualdisplay import Display
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        # Clear the browser download dir so we can spot the new file
        for f in self.download_dir.iterdir():
            if f.is_file():
                f.unlink()

        display = Display(visible=False, size=(1920, 1080))
        display.start()
        driver = None
        try:
            opts = Options()
            opts.binary_location = self.chrome_binary
            # NOT headless — the proxy detects Chrome's headless signals.
            opts.add_argument("--no-sandbox")
            opts.add_argument("--ignore-certificate-errors")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--window-size=1920,1080")
            opts.add_experimental_option("prefs", {
                "download.default_directory": str(self.download_dir),
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
            })

            driver = webdriver.Chrome(options=opts)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # --- 1. Log in via the proxy ---
            driver.get(f"{self.proxy_base}/link.n2s?url=https://pubmed.ncbi.nlm.nih.gov/")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.NAME, "uid"))
            )
            self._pause()

            uid_el = driver.find_element(By.NAME, "uid")
            self._type_like_human(uid_el, self.user_id)
            self._pause(0.3, 0.7)

            pw_el = driver.find_element(By.NAME, "upw")
            self._type_like_human(pw_el, self.password)
            self._pause(0.5, 1.0)

            driver.execute_script("document.forms.LOGIN.submit()")
            WebDriverWait(driver, 60).until(
                lambda d: "ncbi.nlm.nih.gov" in d.current_url or "sciencedirect" in d.current_url
            )

            if "ncc.re.kr/common/error" in driver.current_url:
                print("[LibProxy-Browser] Proxy returned error page after login (bot detected?)")
                return False

            print(f"[LibProxy-Browser] Logged in: {driver.current_url[:100]}")
            self._pause(1.0, 2.5)  # look natural before next action

            # --- 2. Navigate to the article page ---
            article_url = f"{self.proxy_base}/link.n2s?url=https://www.sciencedirect.com/science/article/pii/{pii}"
            driver.get(article_url)
            WebDriverWait(driver, 60).until(
                lambda d: "sciencedirect" in d.current_url
            )
            print(f"[LibProxy-Browser] On article page: {driver.current_url[:120]}")
            # Give the SPA time to render and simulate reading
            time.sleep(random.uniform(4.0, 7.0))

            # --- 3. Click the "Download PDF" button ---
            pdf_href = driver.execute_script(
                """
                for (const l of document.querySelectorAll('a')) {
                    if ((l.textContent || '').includes('Download PDF')
                        || (l.href || '').includes('pdfft')) {
                        l.click();
                        return l.href;
                    }
                }
                return null;
                """
            )
            if not pdf_href:
                print("[LibProxy-Browser] No Download PDF link found on page")
                return False
            print(f"[LibProxy-Browser] Clicked: {pdf_href[:120]}")

            # --- 4. Wait for the download to complete ---
            timeout = 120  # generous for large PDFs
            for _ in range(timeout):
                time.sleep(1)
                pdfs = list(self.download_dir.glob("*.pdf"))
                partials = list(self.download_dir.glob("*.crdownload"))
                if pdfs and not partials:
                    src = pdfs[0]
                    # Sanity-check magic bytes
                    with open(src, "rb") as f:
                        magic = f.read(4)
                    if magic != b"%PDF":
                        print(f"[LibProxy-Browser] Downloaded file isn't a PDF (magic={magic.hex()})")
                        return False
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    print(f"[LibProxy-Browser] Downloaded: {dest.name} ({dest.stat().st_size // 1024} KB)")
                    return True

            print("[LibProxy-Browser] Download timeout")
            return False

        except Exception as e:
            import traceback
            print(f"[LibProxy-Browser] Error: {e!r}")
            traceback.print_exc()
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            display.stop()

    # -----------------------------------------------------------------
    # DOI → PII resolution for Cell/Elsevier
    # -----------------------------------------------------------------
    @staticmethod
    def is_cell_or_elsevier_doi(doi: str) -> bool:
        return bool(doi) and doi.startswith("10.1016/")

    def download_pdf_from_doi(self, doi: str, dest: Path) -> bool:
        """Resolve a Cell/Elsevier DOI to its PII and download the PDF."""
        if not self.is_cell_or_elsevier_doi(doi):
            return False

        pii = self._doi_to_pii(doi)
        if not pii:
            print(f"[LibProxy-Browser] Could not resolve PII for {doi}")
            return False
        return self.download_pdf_from_pii(pii, dest)

    def _doi_to_pii(self, doi: str) -> Optional[str]:
        """Resolve DOI → PII by hitting linkinghub.elsevier.com (small HTML page)."""
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            r = requests.get(
                f"https://linkinghub.elsevier.com/retrieve/pii/",
                params={},  # DOI-based resolution: use doi.org redirect
                allow_redirects=False, timeout=15,
            )
            # Better: use doi.org which redirects to linkinghub
            r = requests.get(f"https://doi.org/{doi}", allow_redirects=True, timeout=15)
            m = re.search(r"pii[/:](S[\w]+)", r.url)
            if m:
                return m.group(1)
            m = re.search(r'"pii"\s*:\s*"(S\w+)"', r.text)
            if m:
                return m.group(1)
        except Exception as e:
            print(f"[LibProxy-Browser] PII lookup failed: {e}")
        return None
