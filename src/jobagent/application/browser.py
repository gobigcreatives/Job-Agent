"""Thin Playwright wrapper. Imports playwright lazily so the rest of the
package (scoring, dedup, query building, tracking, ...) works without a
browser installed — only the live application step needs one.

PLAYWRIGHT_CHROMIUM_PATH can point at a pre-installed Chromium binary (some
hosting environments ship one and skip `playwright install`); when unset,
Playwright uses whatever browser `playwright install chromium` downloaded.
"""
from __future__ import annotations

import os

_CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "div.g-recaptcha",
    "#challenge-form",
    "iframe[title*='challenge']",
    "[data-sitekey]",
]


class BrowserSession:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.page = None

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_kwargs: dict = {"headless": self.headless}
        executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        context = self._browser.new_context(user_agent=(
            "Mozilla/5.0 (compatible; JobAgent/0.1; +autonomous job-search assistant)"
        ))
        self.page = context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def goto(self, url: str, timeout: float = 30000) -> None:
        self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")

    def has_captcha(self) -> bool:
        for selector in _CAPTCHA_SELECTORS:
            if self.page.locator(selector).count() > 0:
                return True
        return False
