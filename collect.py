"""Conservative source checker for London Culture Radar.

Only publishes official event records with explicit dates. No generic venue
listing is treated as an event. Unavailable sources are reported, not bypassed.
"""
import datetime
import html
import json
import re
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("Barbican", "https://www.barbican.org.uk/whats-on"),
    ("Southbank Centre", "https://www.southbankcentre.co.uk/whats-on"),
    ("V&A", "https://www.vam.ac.uk/whatson"),
    ("National Theatre", "https://www.nationaltheatre.org.uk/whats-on/"),
    ("Young Vic", "https://www.youngvic.org/whats-on"),
    ("Tate", "https://www.tate.org.uk/whats-on"),
    ("Royal Academy", "https://www.royalacademy.org.uk/exhibitions-and-events"),
    ("Science Museum", "https://www.sciencemuseum.org.uk/see-and-do"),
    ("Natural History Museum", "https://www.nhm.ac.uk/visit/exhibitions.html"),
    ("British Museum", "https://www.britishmuseum.org/exhibitions-events"),
    ("Whitechapel Gallery", "https://www.whitechapelgallery.org/exhibitions/"),
    ("Sadler's Wells", "https://www.sadlerswells.com/whats-on/"),
]
DISCOVERY_FEEDS = [
    "https://www.culturerss.org/london/barbican_events.xml",
    "https://www.culturerss.org/london/design_museum.xml",
    "https://www.culturerss.org/london/natural_history_museum.xml",
    "https://www.culturerss.org/london/tate_modern.xml",
    "https://www.culturerss.org/london/va_museum.xml",
    "https://www.culturerss.org/london/whitechapel_gallery.xml",
]
VENUE_HOSTS = {"www.barbican.org.uk": "Barbican", "designmuseum.org": "Design Museum", "www.designmuseum.org": "Design Museum", "www.nhm.ac.uk": "Natural History Museum", "www.tate.org.uk": "Tate", "www.vam.ac.uk": "V&A", "www.whitechapelgallery.org": "Whitechapel Gallery"}
EVENT_TYPES = {
    "Event", "ExhibitionEvent", "TheaterEvent", "MusicEvent",
    "DanceEvent", "ChildrensEvent", "VisualArtsEvent",
}
WORDS = ("immersive", "installation", "contemporary", "modern art",
         "theatre", "opera", "ballet", "classical", "family", "children",
         "exhibition", "performance", "digital art")


def datepart(value):
    match = re.match(r"^\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group() if match else None


def flatten_events(value):
    if isinstance(value, list):
        for item in value:
            yield from flatten_events(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if EVENT_TYPES.intersection(types):
            yield value
        for key in ("@graph", "event", "subEvent"):
            if key in value:
                yield from flatten_events(value[key])


def clean_text(value):
    return re.sub(r"<[^>]*>", "", html.unescape(str(value or ""))).strip()


def parse_event(event, venue, today, cutoff):
    title = clean_text(event.get("name"))
    start = datepart(event.get("startDate"))
    end = datepart(event.get("endDate")) or start
    url = event.get("url")
    if isinstance(url, dict):
        url = url.get("@id")
    if not title or not start or not isinstance(url, str):
        return None
    if not url.startswith("https://") or end < today or start > cutoff:
        return None
    description = clean_text(event.get("description"))[:220]
    terms = (title + " " + description).lower()
    family = any(word in terms for word in ("family", "children", "kids"))
    category = ("family" if family else "performance" if any(
        word in terms for word in ("theatre", "opera", "ballet", "concert", "performance", "music")
    ) else "art")
    return {
        "title": title, "venue": venue, "category": category,
        "family_friendly": family, "start_date": start, "end_date": end,
        "opening_hours": "", "verified_time": False, "description": description,
        "url": url, "image_url": None,
        "score": 55 + min(35, sum(8 for word in WORDS if word in terms)),
    }


def extract_html_events(page, venue, today, cutoff):
    # Content on each source's listing page may contain no individual Event
    # objects. This is not an error or a signal that the venue has no events.
    blocks = re.findall(
        r'<script\b[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page, re.I | re.S,
    )
    events = []
    for block in blocks:
        try:
            value = json.loads(block)
        except (ValueError, TypeError):
            continue
        for obj in flatten_events(value):
            record = parse_event(obj, venue, today, cutoff)
            if record:
                events.append(record)
    return events


def feed_candidates(xml_bytes):
    # RSS is discovery only: published dates are NOT event dates.
    root = ET.fromstring(xml_bytes)
    found = []
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        parsed = urllib.parse.urlsplit(link)
        if parsed.scheme == "https" and parsed.hostname in VENUE_HOSTS:
            found.append((VENUE_HOSTS[parsed.hostname], link))
    return found[:12]


def load_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "LondonCultureRadar/0.3 (personal event indexing)"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read(2_000_000)


def main():
    now = datetime.datetime.now(ZoneInfo("Europe/London"))
    today = now.date().isoformat()
    cutoff = (now.date() + datetime.timedelta(days=7)).isoformat()
    prior_path = ROOT / "events.json"
    previous = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    records, failures, checked = [], [], 0
    for venue, url in SOURCES:
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "LondonCultureRadar/0.2 (personal event indexing)"
            })
            with urllib.request.urlopen(request, timeout=12) as response:
                page = response.read(2_000_000).decode("utf-8", "replace")
            checked += 1
            records.extend(extract_html_events(page, venue, today, cutoff))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
            failures.append(f"{venue}: {type(error).__name__}: {error}")
    # Third-party RSS lists can be stale. Fetch official pages and only
    # publish source-confirmed JSON-LD events with explicit event dates.
    candidates = []
    for feed_url in DISCOVERY_FEEDS:
        try:
            candidates.extend(feed_candidates(load_url(feed_url)))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as error:
            failures.append(f"RSS {feed_url}: {type(error).__name__}: {error}")
    visited = set()
    for venue, url in candidates:
        if url in visited:
            continue
        visited.add(url)
        if len(visited) > 48:
            break
        try:
            records.extend(extract_html_events(load_url(url).decode("utf-8", "replace"), venue, today, cutoff))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
            failures.append(f"Official event {venue}: {type(error).__name__}: {error}")
    by_key = {}
    for record in records:
        key = (record["venue"].casefold(), record["title"].casefold(), record["start_date"])
        by_key[key] = record

    # Retain previously documented events only while their dates are still valid;
    # do not mark stale records as freshly verified.
    for record in previous.get("events", []):
        if not isinstance(record, dict):
            continue
        if record.get("end_date", record.get("start_date", "")) < today:
            continue
        if record.get("start_date", "") > cutoff:
            continue
        key = (str(record.get("venue", "")).casefold(),
               str(record.get("title", "")).casefold(),
               record.get("start_date"))
        if key not in by_key:
            retained = dict(record)
            retained["verified_time"] = False
            by_key[key] = retained

    if not by_key:
        print("No trustworthy events extracted; retaining existing published dataset.")
        print(f"Sources accessible: {checked}/{len(SOURCES)}; source errors: {len(failures)}")
        for message in failures:
            print(message)
        raise SystemExit(
            "No events available. Source-specific permitted feeds/adapters are required."
        )

    data = {
        "updated_at": now.isoformat(timespec="minutes"),
        "events": list(by_key.values()),
        "source_errors": failures,
        "sources_checked": len(SOURCES) + len(visited),
    }
    prior_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(by_key)} sourced events; {len(failures)} source errors")


if __name__ == "__main__":
    main()
