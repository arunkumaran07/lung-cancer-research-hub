# Lung Cancer Research Hub

A single-page reference for lung cancer research: open clinical trials (Canadian
sites first, filterable to the United States or worldwide), newly published
papers, data portals, guidelines, funders, patient resources and preprint
servers. Plain HTML and JavaScript, no build step, no framework.

Maintained by Arun Kumaran Anguraj Vadivel, Toronto. It is a research reference,
not medical advice.

## Files

| File | What it is | Edited by |
|---|---|---|
| `index.html` | The page: layout, filters, rendering | hand |
| `curated.json` | Portals, guidelines, funders, patient and preprint links | hand |
| `refresh.py` | Pulls trials and papers into `data/` | hand |
| `data/trials.json` | Open lung cancer studies from ClinicalTrials.gov | the daily refresh |
| `data/papers.json` | Recent PubMed records from the feed searches | the daily refresh |
| `data/meta.json` | Counts, queries and the refresh date | the daily refresh |
| `.github/workflows/refresh.yml` | Runs `refresh.py` once a day and commits `data/` | hand |

## How the refresh works

The *Daily refresh* workflow updates the trials and the paper feed once every
24 hours, starting at about 6:17 am Toronto time. GitHub can delay or drop
scheduled runs when Actions is busy, so the workflow is scheduled every three
hours (at 17 minutes past 2, 5, 8, 11, 14, 17, 20 and 23 UTC). Each scheduled run
calls `refresh.py --daily`, which refreshes only if nothing has been refreshed
yet that Toronto day and it is past 6 am; otherwise it exits in a few seconds.
If the 6:17 run is dropped, the next run three hours later does the refresh.

`refresh.py` uses only the Python standard library:

- **Trials.** Queries the ClinicalTrials.gov API v2 for lung cancer, non-small
  cell or small cell lung cancer with status recruiting or not yet recruiting,
  keeps records that mention the lung in their title, conditions, keywords or
  interventions, and stores a compact record per study (phase, status, sponsor,
  interventions, countries, Canadian sites). It tags each study with subtype,
  biomarkers, modality and disease setting by keyword rules defined at the top
  of the script. Studies that leave recruitment disappear at the next refresh.
  If the registry returns fewer than 500 studies the script stops without
  writing, so a failed query cannot empty the page.
- **Papers.** Runs five PubMed searches (trial reports, guidelines, reviews and
  meta-analyses, proteomics and metabolomics, Canadian authors), each combined
  with a lung cancer term, over the last 14 days of PubMed entry dates (further
  back if the previous refresh was longer ago than that); the first run looks
  back 120 days. New records are added to the top of the feed, and papers leave
  the feed 120 days after they were added.

The workflow also runs when `refresh.py` or the workflow file changes, and it can
be started by hand from **Actions → Daily refresh → Run workflow**. Because each
daily refresh writes a new refresh date, the repository has a commit every day,
which keeps GitHub from switching off the schedule for inactivity. While the
repository is private, each run counts against the account's free Actions minutes
(the skipped runs take about a minute each, roughly 250 minutes a month in all);
public repositories are not charged.

Optional: add a repository secret named `NCBI_EMAIL` with your address. NCBI asks
API users to identify themselves; the script works without it.

Run it locally:

```bash
python3 refresh.py --dry-run    # fetch and report, write nothing
python3 refresh.py              # write data/
python3 refresh.py --daily      # same, but only if not yet refreshed today
python3 refresh.py --backfill   # rebuild the paper feed over 120 days
```

To preview the page locally, serve the folder (the page loads its data with
`fetch`, which browsers block on `file://`):

```bash
python3 -m http.server 8000     # then open http://localhost:8000
```

## Editing

- **Curated links:** edit `curated.json`. Each section holds groups, each group a
  list of `{name, url, desc, where}`.
- **Tag rules:** edit `BIOMARKERS`, `MODALITIES` and `SETTINGS` in `refresh.py`.
- **Paper searches:** edit `FEED_QUERIES`; the labels become the filter chips.

## Going public

GitHub Pages serves private repositories only on paid plans. When the page is
ready: **Settings → General → Danger Zone → Change visibility → Public**, then
**Settings → Pages → Source: Deploy from a branch → `main` / `(root)`**. The site
appears at `https://arunkumaran07.github.io/lung-cancer-research-hub/` within a few minutes.
