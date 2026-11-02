# Mile High Ride Calendar

A list of upcoming bike stuff around Denver (group rides, big rides, bike days,
road closures, races, festivals) plus a calendar feed people can subscribe to.

## How it works

```
data/curated.json   hand-picked events, recurring rides (Critical Mass), "regular rides" list
data/sources.json   live iCal feeds (Bicycle Colorado + Denver club Meetup groups)
web/page.html       the page design
build.py            merges everything → site/
site/               the finished website, ready to host
```

`build.py` writes:

- `site/index.html` and `site/events.json`: the website
- `site/calendar.ics`: the main subscribable calendar (weekly rides left out so it isn't noisy)
- `site/calendar-<category>.ics`: one calendar per category (big, group, social, days, roads, community), plus `calendar-denver.ics` (Denver area only)

## Run it locally

```bash
python3 build.py
```

```bash
python3 -m http.server 8000 --directory site
```

Then open http://localhost:8000.

## Put it online (free, auto-updating)

1. Create a GitHub repo and push this folder to it.
2. In the repo: **Settings → Pages → Source: GitHub Actions**.
3. The workflow in `.github/workflows/build.yml` rebuilds every morning, pulls fresh
   events from the feeds, and publishes to `https://<you>.github.io/<repo>/` (or `https://<org>.github.io/` for a repo named `<org>.github.io`). Live at https://milehighrides.github.io.

Subscribers' calendar apps re-check the feed on their own (usually every few hours to a day).

## Adding events

Edit `data/curated.json`:

- `status: "confirmed"` once the organizer announces the date
- `status: "expected"` for a date estimated from past years. Calendars show these as
  "(expected date)" and update automatically when you change them
- Dates: `"2027-06-30"` for all-day, `"2027-06-30T06:30"` for a start time (Denver time),
  optional `"end"` (inclusive)

To add another live feed (any public `.ics` URL), add an entry to `data/sources.json`.

## Expected dates to confirm

These were estimated from past years on Nov 1, 2026. Check them as organizers announce:
Colorado Bike to Work Day (June 30), Triple Bypass (July 10),
Copper Triangle (Aug 7), Colorado's Ride, Tour de Fat, Denver Century Ride (Sept 25),
Denver Bike Fest, and the Trail Ridge Road / Mount Blue Sky road dates.
