# London Culture Radar

A zero-cost-target static cultural events dashboard, with a daily GitHub Actions refresh.

## Setup
1. Create a public GitHub repository and upload these files.
2. In repository Settings > Pages, choose **GitHub Actions** as source.
3. Under Actions, enable workflows if prompted.
4. Run **Refresh events** manually once to populate `events.json`; then it runs daily.
5. Visit the URL shown in Settings > Pages.

The source collector starts with a small set of public official venue pages. Source sites may change, block automation or prohibit certain reuse; the collector stores only records it can extract with dates and source links. No scraped imagery is republished by default. Expand sources after checking permissions.

No credentials are required for the initial setup. Failure alerts use GitHub Actions notifications (configure notification email in GitHub account settings).

## Local preview
Run `python3 -m http.server 8000` from this directory and open http://localhost:8000.
Run `python3 collect.py` to refresh the event data. Requires `pip install -r requirements.txt`.

## Data quality
A missing or unverified opening time is marked clearly. The site does not claim live ticket availability or precise public-transport times. Journey convenience is initially a rough London-area heuristic, not a routing API. Events are selected for the rolling seven-day window.

## Caveats
- Scheduled GitHub Actions jobs are best-effort, not guaranteed to run at an exact time.
- This is an initial working scaffold, not verified comprehensive coverage of 21 venues.
- The public GitHub repository and published JSON are visible to others; avoid storing private details beyond a broad origin area.
