#!/usr/bin/env python3
"""
Phase A v2: Build Skill Counts
================================

Single-pass scan of all Lightcast Main files (2010-2024, 466M postings).
Streams through raw gzipped CSVs, splits pipe-delimited skills, classifies
employer type (vectorized), and accumulates aggregated counts directly into
per-year checkpoint parquets. No posting-level intermediate is written.

v2 changes from v1:
  - employer_skill.parquet: added naics2, naics4, skill_type columns
  - panel_stats.parquet: fixed remote_type parsing (0=onsite, 1=remote, 2=hybrid, 3=other)
  - employer_skill aggregation key: (county, employer_type, naics2, naics4, skill, skill_type)

For each year, writes:
  intermediate/scan/year=YYYY/
  ├── skill_counts.parquet       (county, skill, skill_type, count)
  ├── employer_skill.parquet     (county, employer_type, naics2, naics4, skill, skill_type, count)
  ├── panel_stats.parquet        (county, posting/skill/characteristic counts)
  └── _SUCCESS                   (marker — year is complete)

Checkpoints per year; skips completed years on restart.
Memory: ~10-15 GB peak (per-year counter dictionaries with expanded keys).
Expected runtime: ~26-30 hours on Sol.
"""

import os
import sys
import gc
import time
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

# ============================================================
# CONFIGURATION
# ============================================================

# Path configuration. Override via environment variables for portability.
#   LIGHTCAST_RAW_DIR   — directory holding the raw Lightcast Main shards
#                         (one subdirectory per year, each with gzipped CSVs)
#   LIGHTCAST_DATA_DIR  — processed-data root; Phase A writes per-year
#                         checkpoints to ${LIGHTCAST_DATA_DIR}/intermediate/scan
# Fallbacks assume the script is run from a checkout that contains ./raw
# and ./processed; on any other layout, set both env vars explicitly.
DATA_BASE = os.environ.get("LIGHTCAST_RAW_DIR", "./raw/Main")
OUTPUT_DIR = os.path.join(
    os.environ.get("LIGHTCAST_DATA_DIR", "./processed"),
    "intermediate", "scan",
)

YEARS = list(range(2010, 2025))  # 2024 is last full year

USECOLS = [
    "posted", "county", "naics4", "naics2",
    "specialized_skills_name", "software_skills_name", "common_skills_name",
    "company", "company_is_staffing",
    "remote_type", "min_edulevels", "job_seniority",
    "is_internship", "duplicates",
]

# Employer type classification
UNIVERSITY_NAICS4 = {"6113", "6112", "6114", "6115", "6116", "6117"}
FEDERAL_LAB_NAICS4 = {"5417", "9271"}

SKILL_COLS = [
    ("specialized_skills_name", "specialized"),
    ("software_skills_name", "software"),
    ("common_skills_name", "common"),
]

EMPLOYER_TYPES = ["corporate", "university", "federal_lab",
                  "government", "staffing", "unclassified"]

# Remote type mapping (Lightcast numeric codes)
# 0=on-site, 1=remote, 2=hybrid, 3=other
REMOTE_MAP = {"0": "onsite", "1": "remote", "2": "hybrid", "3": "other"}


# ============================================================
# HELPERS
# ============================================================

def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


def list_gz_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith(".csv.gz") and os.path.getsize(os.path.join(folder, f)) > 0
    ])


def read_gz(filepath):
    try:
        try:
            return pd.read_csv(
                filepath, compression="gzip",
                usecols=lambda c: c in USECOLS,
                dtype=str, low_memory=False, on_bad_lines="skip",
            )
        except TypeError:
            return pd.read_csv(
                filepath, compression="gzip",
                usecols=lambda c: c in USECOLS,
                dtype=str, low_memory=False,
                error_bad_lines=False, warn_bad_lines=False,
            )
    except Exception as e:
        log(f"      WARN: {os.path.basename(filepath)}: {e}")
        return None


def classify_employer_type(naics4, is_staffing):
    """Vectorized employer type via np.select. Order: first match wins."""
    conditions = [
        naics4 == "9999",
        naics4.isin(UNIVERSITY_NAICS4),
        naics4.isin(FEDERAL_LAB_NAICS4),
        naics4.str.startswith("92"),
        (naics4 == "5613") | (is_staffing == "true"),
    ]
    choices = ["unclassified", "university", "federal_lab", "government", "staffing"]
    return np.select(conditions, choices, default="corporate")


def count_pipe_delimited(series):
    """Count pipe-delimited items. Empty → 0."""
    s = series.fillna("")
    pipe_counts = s.str.count(r"\|")
    return np.where(s != "", pipe_counts + 1, 0).astype(np.int32)


# ============================================================
# PROCESS ONE GZ FILE → UPDATE COUNTERS
# ============================================================

def process_file(filepath, target_year, counters):
    """Read one gz file, update all counter dictionaries in place.

    Returns number of postings processed (for target year).
    """
    df = read_gz(filepath)
    if df is None or len(df) == 0:
        return 0

    # Ensure columns, fill NaN
    for col in USECOLS:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("")

    # Filter to target year
    df = df[df["posted"].str[:4] == str(target_year)]
    if len(df) == 0:
        return 0

    # Filter to valid county (non-empty)
    df = df[df["county"] != ""]
    if len(df) == 0:
        return 0

    n = len(df)

    # Employer type (vectorized)
    is_staffing = df["company_is_staffing"].str.strip().str.lower()
    df["etype"] = classify_employer_type(df["naics4"], is_staffing)

    # Clean NAICS fields
    df["naics4_clean"] = df["naics4"].where(df["naics4"] != "", "9999")
    df["naics2_clean"] = df["naics2"].where(df["naics2"] != "", "99")

    # Unpack counters
    skill_counts = counters["skill_counts"]
    employer_skill = counters["employer_skill"]
    posting_counts = counters["posting_counts"]
    employer_posting = counters["employer_posting"]
    has_skill_counts = counters["has_skill_counts"]
    mention_counts = counters["mention_counts"]
    remote_counts = counters["remote_counts"]
    internship_counts = counters["internship_counts"]

    # --- Posting counts ---
    for county, cnt in df["county"].value_counts().items():
        posting_counts[county] += cnt

    # --- Employer posting counts ---
    ep = df.groupby(["county", "etype"]).size()
    for (county, etype), cnt in ep.items():
        employer_posting[(county, etype)] += cnt

    # --- Remote (fixed: parse numeric codes) ---
    for remote_val, remote_label in REMOTE_MAP.items():
        mask = df["remote_type"] == remote_val
        if mask.any():
            for county, cnt in df.loc[mask, "county"].value_counts().items():
                remote_counts[(county, remote_label)] += cnt

    # --- Internship ---
    intern_mask = df["is_internship"].str.strip().str.lower() == "true"
    if intern_mask.any():
        for county, cnt in df.loc[intern_mask, "county"].value_counts().items():
            internship_counts[county] += cnt

    # --- Skills: split, explode, count ---
    any_skill = pd.Series(False, index=df.index)

    for skill_col, skill_type in SKILL_COLS:
        mask = df[skill_col] != ""
        if not mask.any():
            continue

        any_skill |= mask

        # Mention counts (pre-explode — faster)
        mentions = count_pipe_delimited(df.loc[mask, skill_col])
        for county, total in pd.Series(
            mentions, index=df.loc[mask, "county"].values
        ).groupby(level=0).sum().items():
            mention_counts[(county, skill_type)] += int(total)

        # Explode skills
        sub = df.loc[mask, ["county", "etype", "naics2_clean", "naics4_clean", skill_col]].copy()
        sub["skill"] = sub[skill_col].str.split("|", regex=False)
        sub = sub.explode("skill")
        sub["skill"] = sub["skill"].str.strip()
        sub = sub[sub["skill"] != ""]

        if len(sub) == 0:
            continue

        # Skill counts: (county, skill, skill_type)
        sc = sub.groupby(["county", "skill"]).size()
        for (county, skill), cnt in sc.items():
            skill_counts[(county, skill, skill_type)] += cnt

        # Employer-skill counts: (county, etype, naics2, naics4, skill, skill_type)
        es = sub.groupby(["county", "etype", "naics2_clean", "naics4_clean", "skill"]).size()
        for (county, etype, naics2, naics4, skill), cnt in es.items():
            employer_skill[(county, etype, naics2, naics4, skill, skill_type)] += cnt

        del sub
        gc.collect()

    # --- Has-any-skill counts ---
    if any_skill.any():
        for county, cnt in df.loc[any_skill, "county"].value_counts().items():
            has_skill_counts[county] += cnt

    return n


# ============================================================
# WRITE YEAR CHECKPOINT
# ============================================================

def write_checkpoint(year, counters, checkpoint_dir):
    """Convert counter dicts to DataFrames and write as parquet."""

    os.makedirs(checkpoint_dir, exist_ok=True)

    # 1. skill_counts.parquet (unchanged schema)
    sc = counters["skill_counts"]
    if sc:
        rows = [{"county": k[0], "skill": k[1], "skill_type": k[2], "count": v}
                for k, v in sc.items()]
        pd.DataFrame(rows).to_parquet(
            os.path.join(checkpoint_dir, "skill_counts.parquet"),
            index=False, engine="pyarrow",
        )
        log(f"    skill_counts: {len(rows):,} rows")
    else:
        log(f"    skill_counts: empty")

    # 2. employer_skill.parquet (v2: expanded with naics2, naics4, skill_type)
    es = counters["employer_skill"]
    if es:
        rows = [{"county": k[0], "employer_type": k[1], "naics2": k[2],
                 "naics4": k[3], "skill": k[4], "skill_type": k[5], "count": v}
                for k, v in es.items()]
        df_es = pd.DataFrame(rows)
        # Dictionary encoding for high-cardinality string columns
        df_es.to_parquet(
            os.path.join(checkpoint_dir, "employer_skill.parquet"),
            index=False, engine="pyarrow",
            use_dictionary=["skill", "naics4", "naics2", "employer_type", "skill_type"],
        )
        log(f"    employer_skill: {len(rows):,} rows")
        del df_es
    else:
        log(f"    employer_skill: empty")

    # 3. panel_stats.parquet (v2: fixed remote counts)
    pc = counters["posting_counts"]
    ep = counters["employer_posting"]
    hs = counters["has_skill_counts"]
    mc = counters["mention_counts"]
    rc = counters["remote_counts"]
    ic = counters["internship_counts"]

    counties = sorted(pc.keys())
    panel_rows = []
    for county in counties:
        row = {
            "county": county,
            "total_postings": pc[county],
            "n_has_skill": hs.get(county, 0),
            "mention_specialized": mc.get((county, "specialized"), 0),
            "mention_software": mc.get((county, "software"), 0),
            "mention_common": mc.get((county, "common"), 0),
            # Fixed remote counts
            "n_remote": rc.get((county, "remote"), 0),
            "n_hybrid": rc.get((county, "hybrid"), 0),
            "n_onsite": rc.get((county, "onsite"), 0),
            "n_remote_other": rc.get((county, "other"), 0),
            "n_internship": ic.get(county, 0),
        }
        for etype in EMPLOYER_TYPES:
            row[f"n_{etype}"] = ep.get((county, etype), 0)
        panel_rows.append(row)

    if panel_rows:
        pd.DataFrame(panel_rows).to_parquet(
            os.path.join(checkpoint_dir, "panel_stats.parquet"),
            index=False, engine="pyarrow",
        )
        log(f"    panel_stats: {len(panel_rows):,} counties")

    # Success marker
    Path(os.path.join(checkpoint_dir, "_SUCCESS")).touch()


# ============================================================
# PROCESS ONE YEAR
# ============================================================

def process_year(year):
    """Process all gz files for one year."""

    checkpoint_dir = os.path.join(OUTPUT_DIR, f"year={year}")
    done_marker = os.path.join(checkpoint_dir, "_SUCCESS")

    if os.path.exists(done_marker):
        log(f"  SKIP year {year}: checkpoint exists")
        return 0

    # Find gz files
    year_dir = os.path.join(DATA_BASE, str(year))
    if not os.path.isdir(year_dir):
        log(f"  SKIP year {year}: no data directory")
        return 0

    gz_files = []
    for subdir in sorted(os.listdir(year_dir)):
        subpath = os.path.join(year_dir, subdir)
        if os.path.isdir(subpath):
            gz_files.extend(list_gz_files(subpath))

    if not gz_files:
        log(f"  SKIP year {year}: no gz files")
        return 0

    log(f"  Year {year}: {len(gz_files)} files")

    # Initialize counters
    counters = {
        "skill_counts": Counter(),         # (county, skill, skill_type) → count
        "employer_skill": Counter(),        # (county, etype, naics2, naics4, skill, skill_type) → count
        "posting_counts": Counter(),        # county → total
        "employer_posting": Counter(),      # (county, etype) → count
        "has_skill_counts": Counter(),      # county → postings with any skill
        "mention_counts": Counter(),        # (county, skill_type) → total mentions
        "remote_counts": Counter(),         # (county, remote_label) → count
        "internship_counts": Counter(),     # county → internship postings
    }

    total = 0
    t_start = time.time()

    for i, gz_file in enumerate(gz_files):
        n = process_file(gz_file, year, counters)
        total += n

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            rate = total / elapsed if elapsed > 0 else 0
            # Log employer_skill counter size for memory monitoring
            es_size = len(counters["employer_skill"])
            log(f"    {i+1}/{len(gz_files)} files | "
                f"{total:,} postings | "
                f"{rate:,.0f} rows/sec | "
                f"emp_skill keys: {es_size:,}")

    elapsed = time.time() - t_start
    rate = total / elapsed if elapsed > 0 else 0
    log(f"  Year {year} scanned: {total:,} postings in {elapsed/60:.1f} min "
        f"({rate:,.0f} rows/sec)")

    # Write checkpoint
    log(f"  Writing checkpoint for year {year}...")
    write_checkpoint(year, counters, checkpoint_dir)
    log(f"  Year {year} checkpoint written.")

    # Free memory
    del counters
    gc.collect()

    return total


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 60)
    log("Phase A v2: Build Skill Counts")
    log(f"  Data source: {DATA_BASE}")
    log(f"  Output: {OUTPUT_DIR}")
    log(f"  Years: {YEARS[0]}-{YEARS[-1]}")
    log(f"  v2 changes: expanded employer_skill (naics2/naics4/skill_type),")
    log(f"              fixed remote_type parsing")
    log("=" * 60)
    log("")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    grand_total = 0
    year_totals = {}
    t_grand = time.time()

    for year in YEARS:
        n = process_year(year)
        year_totals[year] = n
        grand_total += n
        log("")

    # Summary
    elapsed = time.time() - t_grand
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"  Total postings scanned: {grand_total:,}")
    log(f"  Total time: {elapsed/3600:.1f} hours")
    if grand_total > 0 and elapsed > 0:
        log(f"  Overall rate: {grand_total/elapsed:,.0f} rows/sec")
    log("")
    log(f"  {'Year':>6}  {'Postings':>14}")
    log(f"  {'-'*6}  {'-'*14}")
    for year in YEARS:
        n = year_totals.get(year, 0)
        log(f"  {year:>6}  {n:>14,}")
    log("")
    log("=" * 60)
    log("Phase A v2 complete.")
    log("=" * 60)


if __name__ == "__main__":
    main()
