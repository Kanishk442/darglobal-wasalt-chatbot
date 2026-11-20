"""Tiny dependency-free retrieval: chunking + BM25 over scraped and seed data."""
import json
import math
import re
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STOP = set("a an the and or of to in on for is are was be by with at as it this that from your you our we i what who how do does can".split())


def tokenize(s: str):
    return [w for w in re.findall(r"[a-z0-9؀-ۿ]+", s.lower()) if w not in STOP]


def chunk(text: str, size: int = 900):
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out


class Index:
    def __init__(self):
        self.docs = []  # dicts: source, url, title, text
        self.tf = []
        self.df = Counter()
        self.avgdl = 0.0
        self.load()

    def load(self):
        pages = []
        for fname in ("seed.json", "scraped.json"):
            p = DATA_DIR / fname
            if p.exists():
                pages += json.loads(p.read_text(encoding="utf-8"))
        self.docs, self.tf, self.df = [], [], Counter()
        for pg in pages:
            for c in chunk(pg["text"]):
                self.docs.append({"source": pg["source"], "url": pg["url"], "title": pg.get("title", ""), "text": c})
        for d in self.docs:
            t = Counter(tokenize(d["title"] + " " + d["text"]))
            self.tf.append(t)
            self.df.update(t.keys())
        self.avgdl = (sum(sum(t.values()) for t in self.tf) / len(self.tf)) if self.tf else 1.0

    PINNED_TITLES = {"About DarGlobal", "About Wasalt", "DarGlobal and Wasalt relationship"}

    def pinned(self):
        return [d for d in self.docs if d["title"] in self.PINNED_TITLES]

    def search(self, query: str, k: int = 5):
        q = tokenize(query)
        n = len(self.docs)
        scored = []
        for i, t in enumerate(self.tf):
            dl = sum(t.values())
            s = 0.0
            for w in q:
                if w in t:
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * t[w] * 2.2 / (t[w] + 1.2 * (0.25 + 0.75 * dl / self.avgdl))
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [self.docs[i] for _, i in scored[:k]]
