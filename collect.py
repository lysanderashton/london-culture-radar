"""London Culture Radar daily event discovery.

Sources: official venue event JSON-LD, independent structured London event feeds,
and culture/news RSS leads. News publication dates are NEVER treated as event dates.
Only events with explicit event dates enter the dated dashboard.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import datetime as dt
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
VENUE_PAGES = [
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
    ("London Museum", "https://www.londonmuseum.org.uk/whats-on/"),
    ("Design Museum", "https://designmuseum.org/exhibitions"),
    ("Serpentine", "https://www.serpentinegalleries.org/whats-on/"),
    ("ICA", "https://www.ica.art/whats-on"),
    ("Hayward Gallery", "https://www.southbankcentre.co.uk/venues/hayward-gallery/"),
    ("Royal Opera House", "https://www.rbo.org.uk/tickets-and-events"),
    ("Wigmore Hall", "https://wigmore-hall.org.uk/whats-on"),
    ("Camden Art Centre", "https://camdenartcentre.org/whats-on"),
]
VENUE_HOSTS = {
    "barbican.org.uk":"Barbican", "southbankcentre.co.uk":"Southbank Centre",
    "vam.ac.uk":"V&A", "nationaltheatre.org.uk":"National Theatre",
    "youngvic.org":"Young Vic", "tate.org.uk":"Tate",
    "royalacademy.org.uk":"Royal Academy", "sciencemuseum.org.uk":"Science Museum",
    "nhm.ac.uk":"Natural History Museum", "britishmuseum.org":"British Museum",
    "whitechapelgallery.org":"Whitechapel Gallery", "sadlerswells.com":"Sadler's Wells",
    "londonmuseum.org.uk":"London Museum", "designmuseum.org":"Design Museum",
    "serpentinegalleries.org":"Serpentine", "ica.art":"ICA",
    "rbo.org.uk":"Royal Ballet and Opera", "wigmore-hall.org.uk":"Wigmore Hall",
    "camdenartcentre.org":"Camden Art Centre",
}
# Broad editorial discovery: venue feeds, visual-arts features, culture news,
# and local reporting. The article publication date is not an event date.
NEWS_RSS = [
    "https://www.artrabbit.com/network/features.rss",
    "https://londonist.com/feed",
    "https://www.ianvisits.co.uk/feed/",
    "https://www.theguardian.com/culture/rss",
    "https://www.theguardian.com/stage/rss",
    "https://www.culturerss.org/london/barbican_events.xml",
    "https://www.culturerss.org/london/natural_history_museum.xml",
    "https://www.culturerss.org/london/tate_modern.xml",
    "https://www.culturerss.org/london/design_museum.xml",
    "https://www.culturerss.org/london/va_museum.xml",
]
STRUCTURED_FEEDS = [
    ("Tickts London", "https://tickts.co.uk/feed/whats-on/london.json"),
    ("Jazz Live UK", "https://clubgre2jazz.com/uk/api/v1/events.json"),
]
EVENT_TYPES = {"Event","ExhibitionEvent","TheaterEvent","MusicEvent",
               "DanceEvent","ChildrensEvent","VisualArtsEvent","Festival"}
KEYWORDS = ("immersive","installation","contemporary","modern art","theatre","opera",
            "ballet","classical","family","children","exhibition","performance",
            "digital art","gallery","museum","art","dance","architecture",
            "photography","concert","festival","jazz","sculpture","interactive")
PERFORMANCE = ("theatre","opera","ballet","concert","performance","dance",
               "recital","music","jazz","orchestra","show","play")
FAMILY = ("family","children","kids","child-friendly","childrens","under 5",
          "under-5","toddlers","young audiences")
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}")
JSONLD_RX = re.compile(r'<script\b[^>]*type\s*=\s*["\x27]application/ld\+json["\x27][^>]*>(.*?)</script>', re.I|re.S)
UA = {"User-Agent":"LondonCultureRadar/0.5 (+https://github.com/lysanderashton/london-culture-radar; respectful indexing)"}

def fetch(url):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Only HTTPS URLs supported")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=11) as response:
        return response.read(2_000_000)

def clean(v):
    return re.sub(r"<[^>]*>", "", html.unescape(str(v or ""))).strip()

def datepart(v):
    m = DATE_RX.match(str(v or ""))
    if not m:
        return None
    try:
        dt.date.fromisoformat(m.group())
        return m.group()
    except ValueError:
        return None

def event_objects(data):
    if isinstance(data, list):
        for x in data:
            yield from event_objects(x)
    elif isinstance(data, dict):
        typ = data.get("@type", [])
        typ = [typ] if isinstance(typ, str) else typ
        if any(str(t).split("/")[-1] in EVENT_TYPES for t in typ):
            yield data
        for field in ("@graph","event","subEvent","events"):
            if field in data:
                yield from event_objects(data[field])

def image_url(value):
    if isinstance(value, list):
        return next((image_url(v) for v in value if image_url(v)), None)
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return value if isinstance(value, str) and value.startswith("https://") else None

def classify(title, desc):
    phrase = (title+" "+desc).lower()
    family = any(w in phrase for w in FAMILY)
    category = "family" if family else "performance" if any(w in phrase for w in PERFORMANCE) else "art"
    return category, family, phrase

def new_record(title, venue, start, end, url, description="", image=None, category=None,
               family=None, verified_time=False, opening_hours="", source="unknown", price=None):
    title = clean(title)
    start = datepart(start)
    end = datepart(end) or start
    if not title or not start or not end or end < start or not isinstance(url, str):
        return None
    if urllib.parse.urlsplit(url).scheme != "https":
        return None
    desc = clean(description)[:240]
    inferred_cat, inferred_family, phrase = classify(title, desc)
    return dict(title=title, venue=clean(venue) or "London venue — confirm location",
                category=category if category in ("art","performance","family") else inferred_cat,
                family_friendly=inferred_family if family is None else bool(family),
                start_date=start,end_date=end,opening_hours=clean(opening_hours),
                verified_time=bool(verified_time), schedule_uncertain=not bool(verified_time),
                description=desc, url=url, image_url=image_url(image), price=clean(price) if price else None,
                score=45+min(45,sum(7 for word in KEYWORDS if word in phrase)),
                source_type=source, source_checked_at=dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat())

def parse_jsonld(page, default_venue, today, horizon, source_url=None):
    found = []
    for blob in JSONLD_RX.findall(page):
        try:
            objs = event_objects(json.loads(html.unescape(blob)))
            for obj in objs:
                place = obj.get("location") or {}
                if isinstance(place, list):
                    place = next((x for x in place if isinstance(x, dict)), {})
                venue = place.get("name") if isinstance(place,dict) else default_venue
                venue = venue or default_venue
                url = obj.get("url") or source_url
                if isinstance(url, dict):
                    url = url.get("@id")
                start = obj.get("startDate")
                end = obj.get("endDate") or start
                # A dated performance is one session; an exhibition's opening
                # dates alone do not establish daily opening/session times.
                record = new_record(obj.get("name"), venue, start, end, url,
                    obj.get("description"), obj.get("image"), source="event_jsonld",
                    verified_time=bool(start and len(str(start))>10 and str(start)[10] in "T "))
                if record and record["end_date"] >= today and record["start_date"] <= horizon:
                    found.append(record)
        except (ValueError,TypeError,AttributeError):
            continue
    return found

def extract_rss_leads(payload, label):
    root = ET.fromstring(payload)
    found = []
    for item in root.findall(".//item")[:60]:
        url = (item.findtext("link") or "").strip()
        title = clean(item.findtext("title"))
        desc = clean(item.findtext("description"))
        if url.startswith("https://") and title:
            found.append((label,url,title,desc))
    # Atom RSS
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom}entry")[:60]:
        link = item.find(f"{atom}link")
        url = link.attrib.get("href", "") if link is not None else ""
        title = clean(item.findtext(f"{atom}title"))
        desc = clean(item.findtext(f"{atom}summary"))
        if url.startswith("https://") and title:
            found.append((label,url,title,desc))
    return found

def parse_structured_feed(data, source, today, horizon):
    """Handle documented London JSON feeds and common event schemas.
    Only explicit event dates are accepted; news/pub dates are never used."""
    if isinstance(data,dict):
        entries = data.get("events") or data.get("items") or data.get("results") or data.get("data") or []
        if isinstance(entries,dict):
            entries = entries.get("events") or entries.get("items") or []
    else:
        entries = data
    if not isinstance(entries,list):
        return []
    output=[]
    for item in entries[:250]:
        if not isinstance(item,dict):
            continue
        venue = item.get("venue") or item.get("location") or ""
        city = str(item.get("city") or "")
        if isinstance(venue,dict):
            city += " " + str(venue.get("city") or venue.get("address") or "")
            venue = venue.get("name") or ""
        where = (str(venue)+" "+city+" "+str(item.get("address") or "")).lower()
        if source=="Jazz Live UK" and "london" not in where:
            continue  # nationwide feed
        if city and "london" not in city.lower() and source=="Tickts London":
            continue
        when = item.get("datetime") or item.get("start_datetime") or item.get("startDate") or item.get("start_date") or item.get("date")
        until = item.get("end_datetime") or item.get("endDate") or item.get("end_date") or when
        url = item.get("link") or item.get("url") or item.get("event_url")
        record = new_record(item.get("title") or item.get("name"),venue,when,until,url,
            item.get("description") or item.get("summary"), item.get("image_url") or item.get("image"),
            source="structured_feed:"+source, verified_time=bool(when and len(str(when))>10),
            price=item.get("price"))
        if record and record["end_date"]>=today and record["start_date"]<=horizon:
            # Avoid off-topic listings from general-purpose aggregators.
            _, _, phrase = classify(record["title"],record["description"])
            if source!="Jazz Live UK" and not any(k in phrase for k in KEYWORDS):
                continue
            output.append(record)
    return output

def key(record):
    return (re.sub(r"\W+","",record["title"].casefold()),
            re.sub(r"\W+","",record["venue"].casefold()),
            record["start_date"])

def parse_date_calendar(markup, calendar_date, page_url):
    """Extract exhibition tiles from IanVisits date-specific open-exhibitions calendar.

    The page states exhibitions are open on calendar_date, but does not establish
    opening hours or ticket availability. This is not an official venue feed.
    """
    soup=BeautifulSoup(markup,"html.parser")
    heading=soup.get_text(" ",strip=True)[:600].lower()
    if "exhibitions open on" not in heading and "exhibitions open today" not in heading:
        return []
    items=[]
    seen=set()
    for header in soup.find_all(["h3","h4"]):
        title=header.get_text(" ",strip=True)
        if len(title)<5 or len(title)>135 or title.casefold() in seen:
            continue
        # Select the smallest parent covering a clearly labelled exhibition
        # closing date, without sweeping up the whole page.
        root=None
        for parent in list(header.parents)[:6]:
            txt=parent.get_text(" ",strip=True)
            if len(txt)>1600:
                break
            if "Exhibition ends on" in txt and len(txt)>len(title)+15:
                root=parent
                break
        if root is None:
            continue
        txt=root.get_text(" ",strip=True)
        if len(txt)>1000:
            continue
        # Exclude navigation and article headings; require a real event link.
        a=header.find("a",href=True) or root.find("a",href=True)
        if not a:
            continue
        url=urllib.parse.urljoin(page_url,a["href"])
        if urllib.parse.urlsplit(url).hostname not in ("www.ianvisits.co.uk","ianvisits.co.uk"):
            continue
        # IanVisits confirms date-level listing, not venue operating hours.
        # Closing date is optional extra evidence, not used to infer a daily schedule.
        venue="London exhibition — see listing"
        location=root.select_one(".venue, .location, [class*=venue], [class*=location]")
        if location:
            possible=location.get_text(" ",strip=True)
            if 3<len(possible)<140:
                venue=possible
        image=root.find("img")
        image=image.get("data-src") or image.get("src") if image else None
        if image:
            image=urllib.parse.urljoin(page_url,image)
        desc=txt.replace(title,"",1)
        desc=re.split("Exhibition ends on",desc)[0].replace("Read more ›","").strip()[:210]
        if not desc:
            desc="Exhibition listed as open on this date by IanVisits."
        record=new_record(title,venue,calendar_date,calendar_date,url,desc,
            image,source="date_calendar:IanVisits",verified_time=False)
        if record:
            record["schedule_uncertain"]=False
            record["calendar_dates"]=[calendar_date]
            record["date_evidence_url"]=page_url
            record["score"]=max(record["score"],58)
            seen.add(title.casefold())
            items.append(record)
    return items


def run(today=None, http_fetch=None, prior=None):
    http_fetch=http_fetch or fetch
    now=dt.datetime.now(ZoneInfo("Europe/London"))
    today=today or now.date().isoformat()
    horizon=(dt.date.fromisoformat(today)+dt.timedelta(days=7)).isoformat()
    previous=prior if prior is not None else json.loads((ROOT/"events.json").read_text())
    records=[]; failures=[]; fetched=0; lead_count=0
    def attempt(url,label):
        nonlocal fetched
        try:
            payload=http_fetch(url)
            fetched+=1
            return payload
        except (urllib.error.HTTPError,urllib.error.URLError,OSError,ValueError,TimeoutError) as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            return None

    def batch(work, limit=10):
        results=[]
        with ThreadPoolExecutor(max_workers=limit) as pool:
            futures={pool.submit(attempt,url,label):(name,url) for name,url,label in work}
            for future in as_completed(futures):
                name,url=futures[future]
                payload=future.result()
                if payload:
                    results.append((name,url,payload))
        return results

    calendar_days=[(dt.date.fromisoformat(today)+dt.timedelta(days=n)).isoformat() for n in range(8)]
    calendar_urls=[(day, f"https://www.ianvisits.co.uk/calendar/date/{day.replace('-', '/')}/exhibitions") for day in calendar_days]
    first = [(name,url,"official "+name) for name,url in VENUE_PAGES]
    first += [(name,url,"structured "+name) for name,url in STRUCTURED_FEEDS]
    first += [("rss",url,"editorial RSS "+url) for url in NEWS_RSS]
    first += [("calendar:"+day,url,"date calendar "+day) for day,url in calendar_urls]
    fetched_items=batch(first)
    leads=[]
    for name,url,payload in fetched_items:
        if name.startswith("calendar:"):
            records.extend(parse_date_calendar(payload.decode("utf-8","replace"),name.split(":",1)[1],url))
        elif name=="rss":
            try:
                leads.extend(extract_rss_leads(payload,url))
            except ET.ParseError as exc:
                failures.append(f"editorial RSS {url}: {exc}")
        elif name in {n for n,_ in STRUCTURED_FEEDS}:
            try:
                records.extend(parse_structured_feed(json.loads(payload),name,today,horizon))
            except (ValueError,TypeError) as exc:
                failures.append(f"structured {name}: invalid JSON: {exc}")
        else:
            records.extend(parse_jsonld(payload.decode("utf-8","replace"),name,today,horizon,url))

    lead_work=[]
    lead_seen=set()
    for source,url,title,desc in leads:
        if url in lead_seen:
            continue
        lead_seen.add(url)
        _,_,phrase=classify(title,desc)
        if not any(word in phrase for word in KEYWORDS):
            continue
        # General arts press covers the world; restrict their leads to
        # articles explicitly mentioning London before fetching them.
        if ("theguardian.com" in source or "artrabbit.com" in source) and "london" not in phrase:
            continue
        if len(lead_work)>=60:
            break
        lead_work.append((source,url,"editorial lead "+source))
    lead_count=len(lead_work)
    for source,url,payload in batch(lead_work):
        records.extend(parse_jsonld(payload.decode("utf-8","replace"),
             "London venue — see listing",today,horizon,url))

    combined={}
    for record in records:
        k=key(record)
        if record.get("calendar_dates"):
            # Join date-specific evidence without claiming that any
            # unlisted intervening day is confirmed open.
            k=("daily_calendar",re.sub(r"\W+","",record["title"].casefold()),
               re.sub(r"\W+","",record["venue"].casefold()))
            if k in combined:
                old=combined[k]
                old["calendar_dates"]=sorted(set(old["calendar_dates"]+record["calendar_dates"]))
                old["start_date"]=min(old["start_date"],record["start_date"])
                old["end_date"]=max(old["end_date"],record["end_date"])
                continue
        combined[k]=record
    fresh=len(combined)
    for old in previous.get("events",[]):
        if not isinstance(old,dict):
            continue
        end=old.get("end_date") or old.get("start_date") or ""
        if end<today:
            continue
        k=key(old)
        if old.get('calendar_dates'):
            retained_days=[day for day in old['calendar_dates'] if today<=day<=horizon]
            if not retained_days:
                continue
            k=('daily_calendar',re.sub(r'\W+','',old['title'].casefold()),re.sub(r'\W+','',old['venue'].casefold()))
        if k not in combined:
            rec=dict(old)
            rec["verified_time"]=False
            rec["schedule_uncertain"]=True
            if rec.get("calendar_dates"):
                rec["calendar_dates"]=retained_days
            combined[k]=rec

    if not fresh:
        # Do not overwrite the published dataset and call it freshly verified.
        raise RuntimeError("No newly dated events extracted; "+str(fetched)+" sources fetched; "+str(len(failures))+" fetch errors")

    output={"updated_at":now.isoformat(timespec="minutes"),
        "events":sorted(combined.values(),key=lambda x:(-(x.get("score") or 0),x["title"])),
        "sources_checked":fetched,
        "fresh_events":fresh,
        "editorial_leads_checked":lead_count,
        "source_errors":failures[:70],
        "notice":f"Daily discovery: {fresh} source-dated events found across official, structured and editorial sources. Times and tickets are not always confirmed; check event links."
    }
    return output

def main():
    result=run()
    (ROOT/"events.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Published {len(result['events'])} events, {result['fresh_events']} fresh; {result['sources_checked']} sources fetched; {len(result['source_errors'])} failures")

if __name__=="__main__":
    main()
