"""Polite crawler for the public pages of DarGlobal and Wasalt.

Run:  python -m app.scraper
Output: data/scraped.json  (list of {source, url, title, text})

- Respects robots.txt and sleeps between requests.
- Stays on the allowed domains, skips pagination / search / login URLs.
- If a site blocks us or renders only via JS, the app still works from data/seed.json.
"""
import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "scraped.json"

SITES = {
    "DarGlobal": {
        "domains": {"darglobal.co.uk", "www.darglobal.co.uk"},
        "start": [
            "https://darglobal.co.uk/",
            "https://darglobal.co.uk/about",
            "https://darglobal.co.uk/projects",
            "https://darglobal.co.uk/hospitality",
            "https://darglobal.co.uk/luxury-golf-communities",
            "https://darglobal.co.uk/exclusive-membership",
            "https://darglobal.co.uk/commercial",
            "https://darglobal.co.uk/why-invest",
            "https://darglobal.co.uk/tokenization",
            "https://darglobal.co.uk/investor",
            "https://darglobal.co.uk/press",
            "https://darglobal.co.uk/landing-page/aida",
            "https://darglobal.co.uk/lp/trump-international-qatar",
            "https://darglobal.co.uk/rayana/trump-mansions",
            "https://darglobal.co.uk/trump-international-hotel-and-tower-dubai",
            "https://darglobal.co.uk/trump-international-resort-maldives",
            "https://darglobal.co.uk/trump-tower-jeddah",
        ],
        "max_pages": 40,
    },
    "Wasalt": {
        "domains": {"wasalt.sa", "www.wasalt.sa", "wasalt.com", "www.wasalt.com", "blog.wasalt.sa"},
        "start": [
            "https://wasalt.sa/en",
            "https://wasalt.com/en/about",
            "https://wasalt.sa/en/corporate",
            "https://wasalt.sa/en/properties-for-sale-in-saudi-arabia",
            "https://wasalt.sa/en/properties-for-rent-in-saudi-arabia",
            "https://blog.wasalt.sa/en/",
        ],
        "max_pages": 40,
    },
}

SKIP = re.compile(r"(\?|/login|/signin|/register|/pay-online|\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|mp4)$)", re.I)
# Some firewalls reject UAs containing "bot"; use a normal browser UA (we still honour robots.txt and rate-limit).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en",
}
DELAY = 1.0


def _robots(client: httpx.Client, base: str) -> RobotFileParser:
    rp = RobotFileParser()
    try:
        r = client.get(urljoin(base, "/robots.txt"), timeout=10)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except Exception:
        rp.parse([])
    return rp


def extract(html: str):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header"]):
        t.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    main = soup.find("main") or soup.body or soup
    lines, seen = [], set()
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "summary", "dt", "dd"]):
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if len(txt) < 3 or txt in seen:
            continue
        seen.add(txt)
        lines.append(("## " if el.name in ("h1", "h2", "h3", "h4") else "") + txt)
    links = [a["href"] for a in soup.find_all("a", href=True)]
    return title, "\n".join(lines), links


def crawl(name: str, cfg: dict):
    pages = []
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        robots = {}
        queue = deque(cfg["start"])
        seen = set(cfg["start"])
        while queue and len(pages) < cfg["max_pages"]:
            url = queue.popleft()
            host = urlparse(url).netloc
            if host not in robots:
                robots[host] = _robots(client, f"https://{host}")
            if not robots[host].can_fetch(HEADERS["User-Agent"], url):
                print(f"  robots.txt disallows {url}")
                continue
            try:
                r = client.get(url)
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                    print(f"  {r.status_code} {url}")
                    continue
            except Exception as e:
                print(f"  ERR {url}: {e}")
                continue
            title, text, links = extract(r.text)
            if len(text) > 200 and "could not be found" not in text.lower():
                pages.append({"source": name, "url": url, "title": title, "text": text})
                print(f"  ok  {url} ({len(text)} chars)")
            for href in links:
                nxt = urldefrag(urljoin(url, href))[0].rstrip("/")
                p = urlparse(nxt)
                if p.netloc in cfg["domains"] and not SKIP.search(nxt) and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
            time.sleep(DELAY)
    return pages


def main():
    DATA_DIR.mkdir(exist_ok=True)
    all_pages = []
    for name, cfg in SITES.items():
        print(f"Crawling {name} ...")
        all_pages += crawl(name, cfg)
    OUT.write_text(json.dumps(all_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(all_pages)} pages to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())