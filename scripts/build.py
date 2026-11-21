#!/usr/bin/env python3
"""Fetch every feed in sources.json and write the static site into site/.

Outputs
  site/data/items.json    stories for the reader page (newest first)
  site/data/health.json   per-feed status from the last run
  site/feeds/*.xml        combined RSS feeds (all + one per section)

Environment
  MAX_AGE_DAYS   keep stories this many days (default 21)
  RSSHUB_BASE    e.g. https://rsshub.example.com  -> also read Instagram accounts
                 through that RSSHub instance (/instagram/user/<handle>). Off when unset.
  WORKERS        parallel downloads (default 24)
"""
import json, os, re, time, html, calendar, concurrent.futures as cf
from datetime import datetime, timezone
from email.utils import format_datetime
import urllib.request
import feedparser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
FEEDS = os.path.join(SITE, "feeds")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
MAX_AGE = int(os.environ.get("MAX_AGE_DAYS", "21")) * 86400
RSSHUB = os.environ.get("RSSHUB_BASE", "").rstrip("/")
WORKERS = int(os.environ.get("WORKERS", "24"))
PER_FEED = 25
UA = "Mozilla/5.0 (compatible; MusicRSSBot/1.0; +https://github.com/)"

SECTIONS = {
    "all": ("Everything", lambda s: True),
    "publications": ("Magazines and publications", lambda s: s["category"] == "Publication"),
    "blogs": ("Blogs and independent sites", lambda s: s["category"] == "Blog / Independent Site"),
    "hiphop": ("Hip-hop and R&B", lambda s: s.get("genre") == "Hip-Hop / R&B"),
    "electronic": ("Electronic and dance", lambda s: s.get("genre") == "Electronic / Dance"),
    "rock": ("Rock, metal and punk", lambda s: s.get("genre") == "Rock / Metal / Punk"),
    "indie": ("Indie and alternative", lambda s: s.get("genre") == "Indie / Alternative"),
    "pop": ("Pop and K-pop", lambda s: s.get("genre") == "Pop"),
    "jazz": ("Jazz and classical", lambda s: s.get("genre") == "Jazz / Classical"),
    "roots": ("Country, folk, roots and blues", lambda s: s.get("genre") == "Country / Folk / Roots / Blues"),
    "global": ("Latin, reggae, African and global", lambda s: s.get("genre") == "Global"),
    "industry": ("Industry, production and gear", lambda s: s.get("genre") == "Industry / Production / Gear"),
    "newsletters": ("Newsletters", lambda s: s["kind"] == "newsletter"),
    "podcasts": ("Podcasts", lambda s: s["kind"] == "podcast"),
    "youtube": ("YouTube channels", lambda s: s["kind"] == "youtube"),
    "instagram": ("Instagram accounts", lambda s: s["kind"] == "instagram"),
}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def clean(text, limit=280):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def image_of(e):
    for key in ("media_thumbnail", "media_content"):
        for m in e.get(key) or []:
            if m.get("url"):
                return m["url"]
    for l in e.get("links") or []:
        if l.get("rel") == "enclosure" and (l.get("type") or "").startswith("image"):
            return l.get("href", "")
    body = (e.get("content") or [{}])[0].get("value", "") or e.get("summary", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', body)
    return m.group(1) if m else ""


def fetch(src):
    url = src["feed"] or (f"{RSSHUB}/instagram/user/{src['instagram']}" if RSSHUB and src["instagram"] else "")
    if not url:
        return src, url, None, "skipped"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(6_000_000)
        parsed = feedparser.parse(body)
        if not parsed.entries:
            return src, url, None, "no stories" if not parsed.bozo else "not a feed"
        return src, url, parsed, "ok"
    except Exception as ex:  # network errors, HTTP errors, timeouts
        return src, url, None, type(ex).__name__ + (f" {getattr(ex, 'code', '')}" if hasattr(ex, "code") else "")


def main():
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(FEEDS, exist_ok=True)
    sources = load(os.path.join(ROOT, "sources.json"), [])
    old = {i["link"]: i for i in load(os.path.join(DATA, "items.json"), {}).get("items", [])}
    now = time.time()
    health, fresh = {}, {}

    with cf.ThreadPoolExecutor(WORKERS) as pool:
        for src, url, parsed, status in pool.map(fetch, sources):
            if status == "skipped":
                continue
            n = 0
            if parsed:
                for e in parsed.entries[:PER_FEED]:
                    link = e.get("link")
                    if not link:
                        continue
                    t = e.get("published_parsed") or e.get("updated_parsed")
                    ts = calendar.timegm(t) if t else old.get(link, {}).get("ts", now)
                    if ts > now + 3600:
                        ts = now
                    fresh[link] = {
                        "title": clean(e.get("title"), 200) or "(untitled)",
                        "link": link,
                        "ts": int(ts),
                        "summary": clean(e.get("summary") or (e.get("content") or [{}])[0].get("value", "")),
                        "image": image_of(e),
                        "source": src["name"],
                        "category": src["category"],
                        "subcategory": src["subcategory"],
                        "genre": src.get("genre", ""),
                        "country": src["country"],
                        "kind": src["kind"],
                    }
                    n += 1
            health[src["name"]] = {"url": url, "status": status, "stories": n}

    items = {**old, **fresh}
    items = [i for i in items.values() if now - i["ts"] < MAX_AGE]
    items.sort(key=lambda i: i["ts"], reverse=True)
    items = items[:8000]

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ok = sum(1 for h in health.values() if h["status"] == "ok")
    with open(os.path.join(DATA, "items.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": stamp, "sources_ok": ok, "sources_tried": len(health), "items": items}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(DATA, "health.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": stamp, "feeds": health}, f, ensure_ascii=False, indent=1)

    by_name = {s["name"]: s for s in sources}
    for key, (title, test) in SECTIONS.items():
        sel = [i for i in items if test(by_name.get(i["source"], i))][:300]
        write_rss(os.path.join(FEEDS, f"{key}.xml"), key, title, sel)
    print(f"{ok}/{len(health)} feeds ok, {len(fresh)} fresh stories, {len(items)} kept")


def write_rss(path, key, title, items):
    esc = lambda s: html.escape(s or "", quote=True)
    self_url = f"{SITE_URL}/feeds/{key}.xml" if SITE_URL else f"feeds/{key}.xml"
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">',
           "<channel>", f"<title>B-Side Music RSS: {esc(title)}</title>",
           f"<link>{esc(SITE_URL or self_url)}</link>",
           f'<atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>',
           f"<description>{esc(title)} from {len(items)} recent stories across the music media directory.</description>",
           f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>"]
    for i in items:
        out += ["<item>", f"<title>{esc(i['source'])}: {esc(i['title'])}</title>", f"<link>{esc(i['link'])}</link>",
                f'<guid isPermaLink="true">{esc(i["link"])}</guid>',
                f"<pubDate>{format_datetime(datetime.fromtimestamp(i['ts'], timezone.utc))}</pubDate>",
                f"<category>{esc(i['subcategory'] or i['category'])}</category>",
                f"<description>{esc(i['summary'])}</description>"]
        if i.get("image"):
            out.append(f'<media:thumbnail url="{esc(i["image"])}"/>')
        out.append("</item>")
    out += ["</channel>", "</rss>"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
