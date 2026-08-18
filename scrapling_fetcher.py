import os
import json
import time
import logging
from typing import Optional, Dict, List, Any

# Attempt to import Playwright
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Attempt to import Scrapling components
try:
    from scrapling import Fetcher, StealthyFetcher
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False

import requests

class SkoolFetcher:
    """
    Handles network requests and scraping of Skool classroom pages.
    Uses standard Playwright as primary engine to easily bypass AWS WAF / Goku challenges.
    Falls back to Scrapling StealthyFetcher or Requests if Playwright is unavailable.
    """

    def __init__(self, cookies_path: Optional[str] = None, wait_seconds: int = 3, headless: bool = True):
        self.cookies_path = cookies_path
        self.wait_seconds = wait_seconds
        self.headless = headless
        self.cookies_dict = self._load_cookies() if cookies_path else {}

    def _load_cookies(self) -> Dict[str, str]:
        """Loads cookies from either JSON or Netscape format file into a dictionary."""
        if not self.cookies_path or not os.path.exists(self.cookies_path):
            logging.warning(f"Archivo de cookies no encontrado: {self.cookies_path}")
            return {}

        cookies = {}
        try:
            with open(self.cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if content.startswith("[") and content.endswith("]"):
                # JSON Format
                json_data = json.loads(content)
                for item in json_data:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        cookies[item["name"]] = item["value"]
            else:
                # Netscape format (.txt)
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        name = parts[5].strip()
                        val = parts[6].strip()
                        cookies[name] = val
            logging.info(f"Cargadas {len(cookies)} cookies exitosamente.")
        except Exception as e:
            logging.error(f"Error leyendo archivo de cookies: {e}")
        return cookies

    def _load_cookies_for_playwright(self) -> List[Dict[str, Any]]:
        """Loads cookies from the cookies file formatted for Playwright context.add_cookies()."""
        if not self.cookies_path or not os.path.exists(self.cookies_path):
            return []

        playwright_cookies = []
        try:
            with open(self.cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if content.startswith("[") and content.endswith("]"):
                # JSON Format
                json_data = json.loads(content)
                for item in json_data:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        domain = item.get("domain") or item.get("host") or ".skool.com"
                        if not domain.startswith(".") and not domain.startswith("http"):
                            domain = "." + domain
                        playwright_cookies.append({
                            "name": item["name"],
                            "value": item["value"],
                            "domain": domain,
                            "path": item.get("path", "/")
                        })
            else:
                # Netscape format (.txt)
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        name = parts[5].strip()
                        val = parts[6].strip()
                        domain = parts[0].strip()
                        if not domain.startswith(".") and not domain.startswith("http"):
                            domain = "." + domain
                        path = parts[2].strip()
                        playwright_cookies.append({
                            "name": name,
                            "value": val,
                            "domain": domain,
                            "path": path
                        })
            logging.info(f"Formateadas {len(playwright_cookies)} cookies para Playwright.")
        except Exception as e:
            logging.error(f"Error leyendo cookies para Playwright: {e}")
        return playwright_cookies

    def _fetch_with_playwright(self, url: str) -> str:
        """Fetches the page content using standard Playwright to bypass WAF challenges."""
        logging.info("Iniciando navegador automatizado (Playwright)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            # Load cookies
            pw_cookies = self._load_cookies_for_playwright()
            if pw_cookies:
                context.add_cookies(pw_cookies)
                
            page = context.new_page()
            logging.info(f"Navegando a la URL con Playwright: {url} ...")
            
            # Navigate and wait for DOM
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            try:
                page.wait_for_selector("#__NEXT_DATA__", timeout=15000)
            except Exception:
                pass
                
            # Additional sleep to let client-side content populate
            time.sleep(self.wait_seconds)
            
            # Get DOM content
            content = page.content()
            browser.close()
            return content

    def fetch_page_html(self, url: str) -> str:
        """
        Fetches the target Skool URL.
        Primary: Playwright (solves WAF challenges).
        Fallback 1: Scrapling StealthyFetcher.
        Fallback 2: Requests.
        """
        logging.info(f"Obteniendo contenido de la URL: {url} ...")

        # Primary method: Playwright
        if HAS_PLAYWRIGHT:
            try:
                return self._fetch_with_playwright(url)
            except Exception as e:
                logging.error(f"Error al usar Playwright: {e}. Intentando fallback...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Referer": "https://www.skool.com/"
        }

        # Fallback 1: Scrapling
        if HAS_SCRAPLING:
            try:
                logging.info("Ejecutando extracción stealth con Scrapling...")
                # Format cookies correctly for Scrapling browser
                scrapling_cookies = self._load_cookies_for_playwright()
                fetcher = StealthyFetcher(headless=self.headless)
                response = fetcher.fetch(url, cookies=scrapling_cookies, headers=headers)
                if response and hasattr(response, "text") and response.text:
                    return response.text
                elif response and hasattr(response, "content"):
                    return response.content.decode("utf-8", errors="ignore")
            except Exception as e:
                logging.error(f"Error al usar Scrapling StealthyFetcher: {e}. Intentando Fetcher estándar...")
                try:
                    fetcher = Fetcher()
                    response = fetcher.fetch(url, cookies=self.cookies_dict, headers=headers)
                    if response and hasattr(response, "text"):
                        return response.text
                except Exception as ex:
                    logging.error(f"Falló Fetcher estándar: {ex}")

        # Fallback 2: Standard requests
        logging.warning("Utilizando adaptador de red HTTP estándar (requests) como último recurso...")
        session = requests.Session()
        session.headers.update(headers)
        for name, val in self.cookies_dict.items():
            session.cookies.set(name, val, domain=".skool.com")

        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
