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
| `curated.json` | Portals, guidelines, funders, advocacy and preprint links | hand |
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

## The live site

The site is public at **https://arunkumaran07.github.io/lung-cancer-research-hub/**,
served by GitHub Pages from the `main` branch (root folder) since 4 November 2026.

