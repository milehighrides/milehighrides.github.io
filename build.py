#!/usr/bin/env python3
"""Build the Mile High Ride Calendar.

Merges hand-curated events (data/curated.json) with live calendar feeds
(data/sources.json), keeps the Denver / Front Range ones, and writes:

  site/index.html           the web page (from web/page.html)
  site/events.json          data for the web page
  site/calendar.ics         the full subscribable calendar
  site/calendar-<cat>.ics   one feed per category

Standard library only. Usage:
  python3 build.py [--site-url https://example.com/] [--offline]
"""
import argparse
import calendar
import datetime as dt
import html
import itertools
import shutil
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
CACHE = DATA / "cache"
TZ = "America/Denver"

CATEGORIES = {
    "big": "Big rides & tours",
    "group": "Group & club rides",
    "social": "Social rides",
    "days": "Bike days",
    "roads": "Road closures",
    "community": "Community & festivals",
}
REGIONS = {"denver": "Denver area", "colorado": "Around Colorado"}


# ---------------------------------------------------------------- ICS reading

def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def unescape(value):
    value = value.replace("\\n", "\n").replace("\\N", "\n")
    return re.sub(r"\\([,;\\])", r"\1", value)


def strip_html(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_ics_date(name_params, value):
    """Return (iso string, all_day bool). Times are kept as Denver local."""
    value = value.strip()
    if "VALUE=DATE" in name_params or re.fullmatch(r"\d{8}", value):
        d = dt.datetime.strptime(value[:8], "%Y%m%d").date()
        return d.isoformat(), True
    if value.endswith("Z"):
        # UTC: convert to Denver using the US DST rule
        t = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        return to_denver(t).strftime("%Y-%m-%dT%H:%M"), False
    t = dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    return t.strftime("%Y-%m-%dT%H:%M"), False


def nth_sunday(year, month, n):
    days = [d for d in calendar.Calendar().itermonthdates(year, month)
            if d.month == month and d.weekday() == 6]
    return days[n - 1]


def to_denver(utc):
    y = utc.year
    dst_start = dt.datetime.combine(nth_sunday(y, 3, 2), dt.time(9))   # 2am MST
    dst_end = dt.datetime.combine(nth_sunday(y, 11, 1), dt.time(8))    # 2am MDT
    offset = -6 if dst_start <= utc < dst_end else -7
    return utc + dt.timedelta(hours=offset)


def parse_ics(text):
    events, cur = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name = key.split(";")[0].upper()
            if name in ("DTSTART", "DTEND"):
                cur[name] = parse_ics_date(key.upper(), value)
            else:
                cur[name] = unescape(value)
    return events


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MileHighRideCalendar/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def map_category(cats, title, default=None):
    c = (cats or "").lower()
    t = title.lower()
    if re.search(r"century|fondo|bypass|triangle|tour of|ride the|rally|multi-day", t + " " + c):
        return "big"
    if re.search(r"party|social|tweed|cranks|cruiser|pints|team night|celebrat|happy hour|santa|dia de|muertos", t):
        return "social"
    if default:
        return default
    if "group rides" in c and "community" not in c:
        return "group"
    return "community"


def region_for(loc, source, places):
    if source.get("region", "auto") != "auto":
        return source["region"]
    low = loc.lower()
    if any(p.lower() in low for p in places["denver"]):
        return "denver"
    if any(p.lower() in low for p in places["colorado"]):
        return "colorado"
    return None  # outside Colorado: skip


def load_feed(source, offline, today, horizon, places):
    cache_file = CACHE / f"{source['id']}.json"
    if offline:
        raw = json.loads(cache_file.read_text()) if cache_file.exists() else []
        print(f"  {source['id']}: using cache ({len(raw)} events)")
    else:
        raw, seen = [], set()
        try:
            for page in range(1, source.get("maxPages", 1) + 1):
                url = source["url"].format(page=page)
                items = parse_ics(fetch(url))
                fresh = [e for e in items if e.get("UID") not in seen]
                if not fresh:
                    break
                for e in fresh:
                    seen.add(e.get("UID"))
                raw.extend(fresh)
                last = max(e["DTSTART"][0][:10] for e in fresh if "DTSTART" in e)
                if last > horizon.isoformat():
                    break
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(raw, indent=1))
            print(f"  {source['id']}: fetched {len(raw)} events")
        except Exception as exc:  # network trouble: fall back to the last good copy
            print(f"  {source['id']}: fetch failed ({exc}); using cache", file=sys.stderr)
            raw = json.loads(cache_file.read_text()) if cache_file.exists() else []

    out = []
    for e in raw:
        if "DTSTART" not in e or "SUMMARY" not in e:
            continue
        loc = e.get("LOCATION", "").replace("\\,", ",")
        title = e["SUMMARY"].strip()
        feed_cats = e.get("CATEGORIES", "")
        if source.get("dropTitles") and re.search(source["dropTitles"], title, re.I):
            continue
        if (source.get("dropCategories") and re.search(source["dropCategories"], feed_cats, re.I)
                and not (source.get("keepIfTitle") and re.search(source["keepIfTitle"], title, re.I))):
            continue
        if source.get("requireKeywords") and not re.search(source["requireKeywords"], title, re.I):
            continue
        region = region_for(loc, source, places)
        if not region:
            continue
        start, all_day = e["DTSTART"]
        end = None
        if "DTEND" in e:
            end, _ = e["DTEND"]
            if all_day:  # ICS all-day end is exclusive; store inclusive
                end = (dt.date.fromisoformat(end) - dt.timedelta(days=1)).isoformat()
                if end <= start:
                    end = None
        if (end or start)[:10] < today.isoformat() or start[:10] > horizon.isoformat():
            continue
        desc = strip_html(e.get("DESCRIPTION", ""))
        if len(desc) > 320:
            desc = desc[:317].rsplit(" ", 1)[0] + "…"
        out.append({
            "id": f"{source['id']}-{re.sub(r'[^a-z0-9]+', '-', e.get('UID', title).lower())[:60]}",
            "title": title,
            "start": start,
            "end": end,
            "allDay": all_day,
            "category": map_category(feed_cats, title, source.get("category")),
            "region": region,
            "status": "confirmed",
            "location": re.sub(r",\s*United States$", "", loc).strip(),
            "url": e.get("URL") or source.get("homepage"),
            "description": desc,
            "source": source["name"],
        })
    return out


# ------------------------------------------------------------- curated + rules

def last_weekday(year, month, weekday):
    last = calendar.monthrange(year, month)[1]
    d = dt.date(year, month, last)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def expand_recurring(rec, today, horizon):
    out = []
    y, m = today.year, today.month
    # Rules: [{"months": [5..10], "lastWeekday": "fri", "time": "18:30"}, ...]
    days = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    while True:
        rule = next((r for r in rec["rules"] if m in r["months"]), None)
        if rule is None:
            raise ValueError(f"{rec['id']}: no rule covers month {m}")
        d = last_weekday(y, m, days[rule["lastWeekday"]])
        if d > horizon:
            break
        if d >= today:
            start = f"{d.isoformat()}T{rule['time']}"
            end_t = dt.datetime.fromisoformat(start) + dt.timedelta(minutes=rec.get("durationMin", 120))
            out.append({
                "id": f"{rec['id']}-{d.isoformat()}",
                "title": rec["title"],
                "start": start,
                "end": end_t.strftime("%Y-%m-%dT%H:%M"),
                "allDay": False,
                "category": rec["category"],
                "region": rec.get("region", "denver"),
                "status": "recurring",
                "location": rec["location"],
                "url": rec.get("url"),
                "description": rec["description"],
                "source": "Curated",
            })
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def load_curated(curated, today, horizon):
    out = []
    for e in curated["events"]:
        all_day = "T" not in e["start"]
        if (e.get("end") or e["start"])[:10] < today.isoformat():
            continue
        if e["start"][:10] > horizon.isoformat():
            continue
        out.append({**{"end": None, "stats": None, "region": "denver"}, **e, "allDay": all_day, "source": "Curated"})
    for rec in curated.get("recurring", []):
        out.extend(expand_recurring(rec, today, horizon))
    return out


# ---------------------------------------------------------------- ICS writing

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Denver
BEGIN:DAYLIGHT
TZOFFSETFROM:-0700
TZOFFSETTO:-0600
TZNAME:MDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0600
TZOFFSETTO:-0700
TZNAME:MST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def esc(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > (75 if not parts else 74):
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += b
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def write_ics(path, events, name, stamp):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Mile High Ride Calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}",
        "X-WR-CALDESC:Bike rides\\, events and road closures around Denver",
        f"X-WR-TIMEZONE:{TZ}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    lines += VTIMEZONE.splitlines()
    for e in events:
        title = e["title"] if e["status"] != "expected" else f"{e['title']} (expected date)"
        desc = e.get("description") or ""
        if e["status"] == "expected":
            desc = "Date not announced yet. Estimated from past years. " + desc
        if e.get("url"):
            desc += f"\n\nMore info: {e['url']}"
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@milehighride", f"DTSTAMP:{stamp}"]
        if e["allDay"]:
            s = dt.date.fromisoformat(e["start"])
            last = dt.date.fromisoformat(e["end"]) if e.get("end") else s
            lines += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{last + dt.timedelta(days=1):%Y%m%d}"]
        else:
            s = dt.datetime.fromisoformat(e["start"])
            en = dt.datetime.fromisoformat(e["end"]) if e.get("end") and "T" in e["end"] else s + dt.timedelta(hours=2)
            lines += [f"DTSTART;TZID={TZ}:{s:%Y%m%dT%H%M%S}", f"DTEND;TZID={TZ}:{en:%Y%m%dT%H%M%S}"]
        lines += [f"SUMMARY:{esc(title)}", f"DESCRIPTION:{esc(desc)}",
                  f"CATEGORIES:{esc(CATEGORIES[e['category']])}",
                  "STATUS:TENTATIVE" if e["status"] == "expected" else "STATUS:CONFIRMED",
                  "TRANSP:TRANSPARENT"]
        if e.get("location"):
            lines.append(f"LOCATION:{esc(e['location'])}")
        if e.get("url"):
            lines.append(f"URL:{e['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(fold(l) for l in lines) + "\r\n", encoding="utf-8")


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default="", help="public base URL, used for calendar links")
    ap.add_argument("--offline", action="store_true", help="use cached feeds, no network")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    horizon = today + dt.timedelta(days=400)
    curated = json.loads((DATA / "curated.json").read_text())
    sources = json.loads((DATA / "sources.json").read_text())

    places = {"denver": sources["denverPlaces"], "colorado": sources["coloradoPlaces"]}
    print("Loading feeds…")
    events = load_curated(curated, today, horizon)
    for src in sources["feeds"]:
        try:
            events.extend(load_feed(src, args.offline, today, horizon, places))
        except Exception as exc:  # one broken feed shouldn't stop the build
            print(f"  {src['id']}: skipped ({exc})", file=sys.stderr)

    # Drop feed events that duplicate a curated one (same day, similar title)
    def key(e):
        return (e["start"][:10], re.sub(r"[^a-z]", "", e["title"].lower())[:14])
    seen, merged = set(), []
    for e in events:
        k = key(e)
        if k in seen:
            continue
        seen.add(k)
        merged.append(e)
    merged.sort(key=lambda e: (e["start"], e["title"]))

    # Flag weekly series (4+ dates, a week or less apart). The page hides them
    # by default and the main calendar leaves them out; the category feed keeps them.
    by_title = {}
    for e in merged:
        by_title.setdefault(e["title"], []).append(e)
    for series in by_title.values():
        days = [dt.date.fromisoformat(e["start"][:10]) for e in series]
        weekly = len(days) >= 4 and min((b - a).days for a, b in zip(days, days[1:])) <= 8
        for e in series:
            e["weekly"] = weekly

    SITE.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_ics(SITE / "calendar.ics", [e for e in merged if not e["weekly"]],
              "Mile High Ride Calendar", stamp)
    write_ics(SITE / "calendar-denver.ics",
              [e for e in merged if not e["weekly"] and e["region"] == "denver"],
              "Mile High Rides: Denver area only", stamp)
    for old in SITE.glob("calendar-*.ics"):
        if old.stem.split("-", 1)[1] not in list(CATEGORIES) + ["denver"]:
            old.unlink()
    for cat, label in CATEGORIES.items():
        subset = [e for e in merged if e["category"] == cat]
        write_ics(SITE / f"calendar-{cat}.ics", subset, f"Mile High Rides: {label}", stamp)

    # One feed for every mix of categories, so subscribers can pick exactly what
    # they want. Named feeds/<cats in CATEGORIES order>[-denver][-weekly].ics
    feeds = SITE / "feeds"
    if feeds.exists():
        shutil.rmtree(feeds)
    feeds.mkdir()
    keys = list(CATEGORIES)
    for picked in (c for r in range(1, len(keys) + 1) for c in itertools.combinations(keys, r)):
        for denver_only in (False, True):
            for weekly in (False, True):
                subset = [e for e in merged
                          if e["category"] in picked
                          and (weekly or not e["weekly"])
                          and (not denver_only or e["region"] == "denver")]
                labels = "All categories" if len(picked) == len(keys) else ", ".join(CATEGORIES[c] for c in picked)
                name = f"Mile High Rides: {labels}" + (" (Denver area)" if denver_only else "")
                stem = "-".join(picked) + ("-denver" if denver_only else "") + ("-weekly" if weekly else "")
                write_ics(feeds / f"{stem}.ics", subset, name, stamp)

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "siteUrl": args.site_url,
        "categories": CATEGORIES,
        "regions": REGIONS,
        "sources": [{"name": s["name"], "url": s["homepage"]} for s in sources["feeds"]],
        "events": merged,
        "regular": curated.get("regular", []),
    }
    (SITE / "events.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    page = (ROOT / "web" / "page.html").read_text()
    (SITE / "index.html").write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}</style>\n'
        + page.replace("<header", "</head>\n<body>\n<header", 1) + "\n</body>\n</html>\n")
    counts = {c: sum(e["category"] == c for e in merged) for c in CATEGORIES}
    print(f"Wrote {len(merged)} events → site/  {counts}")


if __name__ == "__main__":
    main()
