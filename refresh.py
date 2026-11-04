#!/usr/bin/env python3
"""Refresh the data files behind the Lung Cancer Research Hub.

Writes three files and touches nothing else:
  data/trials.json  open lung cancer studies from ClinicalTrials.gov (API v2)
  data/papers.json  recent PubMed records matching the feed queries below
  data/meta.json    counts and the date of the last refresh

Run locally:   python3 refresh.py
Dry run:       python3 refresh.py --dry-run     (fetch and report, write nothing)
Rebuild feed:  python3 refresh.py --backfill    (look back FEED_DAYS for papers)

Standard library only, so the GitHub Action needs no installs.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TOOL = "lung-cancer-research-hub"
# NCBI asks API users to identify themselves. Set the NCBI_EMAIL repository
# secret to do so; the script works without it, at a lower rate limit.
CONTACT_EMAIL = os.environ.get("NCBI_EMAIL", "")

CT_URL = "https://clinicaltrials.gov/api/v2/studies"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# ------------------------------------------------------------------ trials

CT_CONDITION = "lung cancer OR non-small cell lung cancer OR small cell lung cancer"
CT_STATUSES = "RECRUITING|NOT_YET_RECRUITING"
CT_PAGE = 200
MIN_EXPECTED_TRIALS = 500   # a registry answer far below this means a failed query

PHASES = {"EARLY_PHASE1": "Early 1", "PHASE1": "1", "PHASE2": "2",
          "PHASE3": "3", "PHASE4": "4", "NA": "N/A"}

# Biomarker tags: matched against title, conditions, keywords and interventions
# (not eligibility text, which lists exclusions as often as inclusions).
BIOMARKERS = [
    ("EGFR", r"\begfr\b|osimertinib|lazertinib|amivantamab|gefitinib|erlotinib|afatinib|"
             r"furmonertinib|firmonertinib|aumolertinib|befotertinib|sunvozertinib"),
    ("ALK", r"\balk\b|alectinib|lorlatinib|brigatinib|ensartinib|ceritinib"),
    ("ROS1", r"\bros-?1\b|repotrectinib|taletrectinib"),
    ("KRAS", r"\bkras\b|sotorasib|adagrasib|divarasib|olomorasib|glecirasib"),
    ("MET", r"\bc-?met\b|\bmet (?:exon|ex14|amplif|alter|overexpress|inhibit|mutat|fusion|positive)"
            r"|\bmetex14\b|capmatinib|tepotinib|savolitinib|telisotuzumab"),
    ("RET", r"\bret\b|selpercatinib|pralsetinib"),
    ("HER2", r"\bher-?2\b|\berbb2\b|zongertinib|trastuzumab"),
    ("BRAF", r"\bbraf\b|dabrafenib|encorafenib"),
    ("NTRK", r"\bn?trk\b|\bntrk[123]?\b|larotrectinib|entrectinib"),
    ("PD-L1", r"\bpd-?l1\b"),
    ("DLL3", r"\bdll3\b|tarlatamab"),
    ("TROP2", r"\btrop-?2\b|datopotamab|sacituzumab"),
]

# Modality tags; a study can carry several.
MODALITIES = [
    ("Immunotherapy", ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab",
                       "cemiplimab", "ipilimumab", "tremelimumab", "tislelizumab",
                       "toripalimab", "sintilimab", "camrelizumab", "serplulimab",
                       "ivonescimab", "pd-1", "pd-l1", "ctla-4", "checkpoint",
                       "immunotherap", "car-t", "car t", "tarlatamab", "bispecific",
                       "vaccine", "til ", "tumor infiltrating", "nk cell"]),
    ("Antibody-drug conjugate", ["antibody-drug conjugate", "antibody drug conjugate",
                                 " adc", "deruxtecan", "govitecan", "vedotin",
                                 "datopotamab", "sacituzumab", "telisotuzumab"]),
    ("Targeted therapy", ["osimertinib", "lazertinib", "amivantamab", "alectinib",
                          "lorlatinib", "brigatinib", "crizotinib", "entrectinib",
                          "repotrectinib", "sotorasib", "adagrasib", "divarasib",
                          "selpercatinib", "pralsetinib", "capmatinib", "tepotinib",
                          "dabrafenib", "trametinib", "encorafenib", "larotrectinib",
                          "zongertinib", "furmonertinib", "firmonertinib", "befotertinib",
                          "aumolertinib", "tyrosine kinase", " tki", "kinase inhibitor"]),
    ("Chemotherapy", ["carboplatin", "cisplatin", "pemetrexed", "docetaxel",
                      "paclitaxel", "etoposide", "gemcitabine", "vinorelbine",
                      "lurbinectedin", "topotecan", "chemotherap"]),
    ("Radiation", ["radiotherapy", "radiation", "sbrt", "sabr", "stereotactic",
                   "proton", "chemoradi", "irradiation"]),
    ("Surgery", ["surgery", "surgical", "resection", "lobectomy", "segmentectomy",
                 "thoracoscopic", "vats", "robotic-assisted"]),
    ("Screening and early detection", ["screening", "early detection", "low-dose ct",
                                       "low dose ct", "ldct", "nodule"]),
    ("Diagnostics and biomarkers", ["ctdna", "liquid biopsy", "cell-free", "biomarker",
                                    "sequencing", "diagnostic", "radiomic",
                                    "proteom", "metabolom", "breath test", "imaging", " pet ", "pet-ct", "pet/ct"]),
    ("Supportive and survivorship", ["quality of life", "exercise", "rehabilitation",
                                     "palliative", "symptom", "smoking cessation",
                                     "nutrition", "psycholog", "survivorship",
                                     "cachexia"]),
]

SETTINGS = [
    ("Early stage", r"early[- ]stage|\bresectable|\bstage i[ab]?\b|\bstage ii[ab]?\b|stage i-ii"
                    r"|neoadjuvant|\badjuvant|perioperative"),
    ("Locally advanced", r"locally advanced|\bstage iii[abc]?\b|limited[- ]stage|chemoradi"),
    ("Advanced or metastatic", r"metastatic|(?<!locally )advanced|\bstage iv[ab]?\b"
                               r"|extensive[- ]stage|recurrent|refractory|previously treated"
                               r"|second[- ]line|first[- ]line"),
]

LUNG_WORDS = ("lung", "nsclc", "sclc", "pulmonary", "thoracic", "bronch")


def fetch_json(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": TOOL})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001 - retried, then raised
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1} after {exc}", file=sys.stderr)
            time.sleep(4 * (attempt + 1))
    return None


def subtype_of(text):
    low = text.lower()
    small = bool(re.search(r"(?<!non-)(?<!non )\bsmall[- ]cell\b|\bsclc\b", low))
    nonsmall = bool(re.search(r"non[- ]small[- ]cell|\bnsclc\b", low))
    out = []
    if nonsmall:
        out.append("NSCLC")
    if small:
        out.append("SCLC")
    if re.search(r"mesothelioma", low):
        out.append("Mesothelioma")
    if re.search(r"\bthymic\b|thymoma|thymic carcinoma", low):
        out.append("Thymic")
    return out or ["Lung cancer, unspecified"]


def tags(text, table):
    low = " " + text.lower() + " "
    return [name for name, words in table if any(w in low for w in words)]


def biomarkers(text):
    low = text.lower()
    return [name for name, pat in BIOMARKERS if re.search(pat, low)]


def phase_label(phases):
    if not phases:
        return "N/A"
    labs = [PHASES.get(p, p) for p in phases]
    if len(labs) == 2 and labs[0].isdigit() and labs[1].isdigit():
        return labs[0] + "/" + labs[1]
    return labs[0]


def parse_study(study):
    """Turn one ClinicalTrials.gov v2 study into a compact hub record."""
    ps = study.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    nct = ident.get("nctId")
    if not nct:
        return None
    status_mod = ps.get("statusModule", {})
    design = ps.get("designModule", {})
    conds = ps.get("conditionsModule", {})
    arms = ps.get("armsInterventionsModule", {})
    desc = ps.get("descriptionModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
    locations = ps.get("contactsLocationsModule", {}).get("locations", []) or []

    interventions = [i.get("name", "").strip() for i in arms.get("interventions", []) or []
                     if i.get("name")]
    conditions = conds.get("conditions", []) or []
    keywords = conds.get("keywords", []) or []
    title = ident.get("briefTitle", "").strip()
    official = ident.get("officialTitle", "") or ""

    core = " ".join([title, official] + conditions + keywords + interventions)
    wide = core + " " + (desc.get("briefSummary", "") or "")[:1500]

    # Basket and pan-tumour studies mention lung only in passing; keep them,
    # but skip records with no lung signal at all (registry synonym drift).
    if not any(w in core.lower() for w in LUNG_WORDS):
        return None

    countries = sorted({(l.get("country") or "").strip() for l in locations if l.get("country")})
    ca_sites = []
    for l in locations:
        if (l.get("country") or "") == "Canada":
            ca_sites.append([l.get("facility", "") or "", l.get("city", "") or "",
                             l.get("state", "") or ""])
    ca_sites.sort(key=lambda s: (s[2], s[1], s[0]))

    status = status_mod.get("overallStatus", "")
    return {
        "id": nct,
        "t": title,
        "ph": phase_label(design.get("phases")),
        "st": "R" if status == "RECRUITING" else "N",
        "ty": {"INTERVENTIONAL": "I", "OBSERVATIONAL": "O"}.get(design.get("studyType", ""), "X"),
        "sp": sponsor,
        "iv": [n for n in interventions if len(n) <= 70][:4],
        "sub": subtype_of(core),
        "bm": biomarkers(core),
        "mod": tags(wide, MODALITIES),
        "set": [n for n, p in SETTINGS if re.search(p, wide.lower())],
        "co": countries,
        "ns": len(locations),
        "ca": ca_sites,
        "sd": (status_mod.get("startDateStruct", {}) or {}).get("date", ""),
        "up": (status_mod.get("lastUpdatePostDateStruct", {}) or {}).get("date", ""),
    }


def fetch_trials():
    params = {
        "query.cond": CT_CONDITION,
        "filter.overallStatus": CT_STATUSES,
        "pageSize": str(CT_PAGE),
        "countTotal": "true",
        "format": "json",
    }
    out, token, total, pages = {}, None, None, 0
    while True:
        q = dict(params)
        if token:
            q["pageToken"] = token
        data = fetch_json(CT_URL + "?" + urllib.parse.urlencode(q))
        if total is None:
            total = data.get("totalCount")
        for study in data.get("studies", []):
            rec = parse_study(study)
            if rec:
                out[rec["id"]] = rec
        pages += 1
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(0.4)
    print(f"registry: {total} matching, {len(out)} kept after lung filter, {pages} pages")
    return out


# ------------------------------------------------------------------ papers

PM_BASE = ('(lung neoplasms[mh] OR "lung cancer"[tiab] OR NSCLC[tiab] OR '
           '"small cell lung"[tiab])')
FEED_QUERIES = [
    ("Trial reports", "(Clinical Trial, Phase II[pt] OR Clinical Trial, Phase III[pt] "
                      "OR Randomized Controlled Trial[pt])"),
    ("Guidelines", '(Practice Guideline[pt] OR Guideline[pt] OR "consensus statement"[ti])'),
    ("Reviews and meta-analyses", "(Systematic Review[pt] OR Meta-Analysis[pt])"),
    ("Proteomics and metabolomics", '(proteom*[tiab] OR metabolom*[tiab] OR lipidom*[tiab] '
                                    'OR "mass spectrometry"[tiab])'),
    ("Canadian authors", "Canada[ad]"),
]
FEED_DAYS = 120        # papers older than this (by PubMed entry date) leave the feed
DAILY_LOOKBACK = 14    # how far back each daily run searches
FEED_MAX = 600


def eutils(path, extra):
    p = {"tool": TOOL, "retmode": "json"}
    if CONTACT_EMAIL:
        p["email"] = CONTACT_EMAIL
    p.update(extra)
    time.sleep(0.4)   # stay under NCBI's 3 requests per second without a key
    return fetch_json(f"{EUTILS}/{path}?" + urllib.parse.urlencode(p))


def search_ids(term, days):
    res = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "datetype": "edat",
                                  "reldate": str(days), "retmax": "400", "sort": "pub_date"})
    return res.get("esearchresult", {}).get("idlist", [])


def summaries(ids):
    out = {}
    for k in range(0, len(ids), 150):
        chunk = ids[k:k + 150]
        res = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(chunk)}).get("result", {})
        for pmid in chunk:
            rec = res.get(pmid)
            if isinstance(rec, dict):
                out[pmid] = rec
    return out


def paper_record(pmid, rec, cats, today):
    authors = rec.get("authors") or []
    who = authors[0].get("name", "") if authors else ""
    if len(authors) > 1:
        who += " et al."
    doi = next((a.get("value", "") for a in rec.get("articleids", [])
                if a.get("idtype") == "doi"), "")
    title = re.sub(r"<[^>]+>", "", (rec.get("title") or "").strip()).rstrip(".")
    pubdate = (rec.get("sortpubdate") or "")[:10].replace("/", "-")
    return {"pmid": pmid, "t": title, "a": who, "j": rec.get("source", ""),
            "d": pubdate, "doi": doi, "c": sorted(cats), "add": today}


def fetch_papers(existing, days):
    today = date.today().isoformat()
    found = {}
    for label, clause in FEED_QUERIES:
        ids = search_ids(f"{PM_BASE} AND {clause}", days)
        print(f"pubmed [{label}]: {len(ids)} in last {days} days")
        for pmid in ids:
            found.setdefault(pmid, set()).add(label)

    by_id = {p["pmid"]: p for p in existing}
    new_ids = [i for i in found if i not in by_id]
    for pmid, cats in found.items():          # a known paper may gain a category
        if pmid in by_id:
            by_id[pmid]["c"] = sorted(set(by_id[pmid].get("c", [])) | cats)
    recs = summaries(new_ids) if new_ids else {}
    for pmid in new_ids:
        if pmid in recs:
            by_id[pmid] = paper_record(pmid, recs[pmid], found[pmid], today)

    cutoff = (date.today() - timedelta(days=FEED_DAYS)).isoformat()
    kept = [p for p in by_id.values() if p.get("add", "") >= cutoff]
    kept.sort(key=lambda p: (p.get("d", ""), p["pmid"]), reverse=True)
    return kept[:FEED_MAX], len([i for i in new_ids if i in recs])


# ------------------------------------------------------------------ I/O

def load(name, default):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")


def main():
    dry = "--dry-run" in sys.argv
    backfill = "--backfill" in sys.argv

    old_trials = {t["id"]: t for t in load("trials.json", [])}
    old_papers = load("papers.json", [])

    fresh = fetch_trials()
    if len(fresh) < MIN_EXPECTED_TRIALS:
        sys.exit(f"only {len(fresh)} trials returned; refusing to overwrite the data")
    added = sorted(set(fresh) - set(old_trials))
    closed = sorted(set(old_trials) - set(fresh))

    days = FEED_DAYS if (backfill or not old_papers) else DAILY_LOOKBACK
    papers, new_papers = fetch_papers(old_papers, days)

    trials = sorted(fresh.values(), key=lambda t: (t["st"], t["id"]), reverse=False)
    meta = {
        "refreshed": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trials": len(trials),
        "trials_canada": sum(1 for t in trials if t["ca"]),
        "trials_added": len(added) if old_trials else 0,
        "trials_closed": len(closed),
        "papers": len(papers),
        "papers_added": new_papers,
        "ct_condition": CT_CONDITION,
        "feed_queries": [{"label": l, "query": f"{PM_BASE} AND {c}"} for l, c in FEED_QUERIES],
        "feed_days": FEED_DAYS,
    }
    print(json.dumps({k: v for k, v in meta.items() if k not in ("feed_queries",)}, indent=1))
    if dry:
        print("dry run: nothing written")
        return
    dump("trials.json", trials)
    dump("papers.json", papers)
    dump("meta.json", meta)
    print("data written")


if __name__ == "__main__":
    main()
