# Rides to confirm each season

Events on the calendar whose dates are estimated (shown as "expected"),
and where to check for the real dates. Update `data/curated.json` when
a date is confirmed, moved or cancelled.

## Lookout Mountain Full Moon Ride (Golden)

- **Estimated:** the evening closest to each full moon, May to October, 9pm,
  meeting at the Pillars at the bottom of Lookout Mountain Road.
  Set in `data/curated.json` → `recurring` → `lookout-full-moon`.
- **Season is a guess.** Nobody has published one. Confirm which months it
  actually runs and change `fullMoon.months` to match.
- **Checked automatically every day.** The daily update reads Golden Today's
  public events calendar (`goldenToday` in `data/curated.json`). When the ride
  appears there (usually a few days ahead), that date switches from "expected"
  to "confirmed" with the posted time, place and link, replacing the month's
  estimate. This works in any month, so it also catches rides outside the
  guessed season.
- **Where it gets announced:**
  - Facebook group: https://www.facebook.com/groups/1675606382710552/
  - Golden Today events: https://www.goldentoday.com/ (search "full moon ride")
  - Avid Cyclist events: https://avidcyclist.com/event/lookout-mountain-full-moon-ride/
  - Cycling lawyer / bike law event pages in Colorado (search "Lookout Mountain full moon ride")
  - A web search for "Lookout Mountain full moon ride <month> <year>"
- **Known past dates:** June 10, 2025 (Avid Cyclist); September 26, 2026 (Golden Today, "Harvest Moon edition").
- **To confirm a date:** add it under `events` with the exact same title,
  `"status": "confirmed"`, the real date and time, and the announcement link.
  It automatically replaces that month's estimate. If a month is announced as
  cancelled or the season turns out different, change `fullMoon.months`.
- **Manual check (optional):** early each spring, look at the sources above to
  learn the real season and update `fullMoon.months`.
