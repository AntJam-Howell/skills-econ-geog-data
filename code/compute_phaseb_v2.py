#!/usr/bin/env python3
"""
Phase B v2: Employer-Type RCA, Institution-Type RCA, Employer Dynamics
========================================================================

Reads Phase A v2 checkpoints (with naics2, naics4, skill_type in employer_skill)
and computes:

  1. Employer-type RCA per (county, employer_type, skill, year)
  2. Institution-type RCA per (county, naics4, skill, year) for univ/lab NAICS
  3. Employer-type dynamics (churning + cosine distance within employer type)
  4. Updates county_year_panel with:
     - share_remote, share_hybrid, share_onsite (from fixed remote)
     - {etype}_n_rca_skills, {etype}_churning_*, {etype}_cosine_distance

Min count filter: 3 (drop county-emp-skill cells with < 3 postings before RCA).

Outputs:
  panels/employer_rca/year=YYYY/employer_rca.parquet
  panels/institution_type_rca/year=YYYY/institution_type_rca.parquet
  panels/employer_dynamics.parquet
  panels/county_year_panel.parquet   (updated — new columns appended)

Preserves: county_skill_year.parquet, skill_relatedness_YYYY.parquet,
           existing 106 columns in county_year_panel.

Expected runtime: ~1-2 hours on Sol.
"""

import os
import sys
import time
import gc
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# CONFIGURATION
# ============================================================

# Path configuration. Override via the LIGHTCAST_DATA_DIR environment
# variable; fallback assumes the script is run from a checkout that
# contains ./processed (the shared root used by Phase A and Phase B).
BASE_DIR = os.environ.get("LIGHTCAST_DATA_DIR", "./processed")
SCAN_DIR = os.path.join(BASE_DIR, "intermediate/scan")
PANEL_DIR = os.path.join(BASE_DIR, "panels")
EMP_RCA_DIR = os.path.join(PANEL_DIR, "employer_rca")
INST_RCA_DIR = os.path.join(PANEL_DIR, "institution_type_rca")

YEARS = list(range(2010, 2025))

EMPLOYER_TYPES = ["corporate", "university", "federal_lab",
                  "government", "staffing"]

# Institution-type analysis: NAICS-4 codes within university and federal_lab
UNIVERSITY_NAICS4 = {"6113", "6112", "6114", "6115", "6116", "6117"}
FEDERAL_LAB_NAICS4 = {"5417", "9271"}
INSTITUTION_NAICS4 = UNIVERSITY_NAICS4 | FEDERAL_LAB_NAICS4

MIN_COUNT = 3
RCA_THRESHOLD = 1.0


# ============================================================
# HELPERS
# ============================================================

def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


def safe_div(a, b, fill=0.0):
    return np.where(b != 0, a / b, fill)


def cosine_sim(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return np.nan
    return float(np.dot(a, b) / (na * nb))


# ============================================================
# STAGE 1: EMPLOYER-TYPE RCA (per year)
# ============================================================

def compute_employer_rca_year(year):
    """Compute employer-type-specific RCA for one year.

    RCA_e(c,s) = [count_e(c,s) / total_e(c)] / [national_e(s) / national_e_total]

    Returns DataFrame written to employer_rca/year=YYYY/.
    """
    emp_path = os.path.join(SCAN_DIR, f"year={year}", "employer_skill.parquet")
    if not os.path.exists(emp_path):
        log(f"  SKIP {year}: no employer_skill checkpoint")
        return None

    emp = pd.read_parquet(emp_path)
    log(f"  {year}: loaded {len(emp):,} employer_skill rows")

    # Filter to target employer types only (exclude unclassified)
    emp = emp[emp["employer_type"].isin(EMPLOYER_TYPES)].copy()

    # Aggregate counts to (county, employer_type, skill, skill_type)
    # (The raw file has one row per county-emp-naics2-naics4-skill-skill_type —
    #  we collapse naics2/naics4 here, since this is the employer-type aggregate.)
    agg = (emp.groupby(["county", "employer_type", "skill", "skill_type"],
                       observed=True)["count"].sum().reset_index())

    # Apply min count filter
    agg = agg[agg["count"] >= MIN_COUNT].copy()

    # RCA denominators (employer-type-specific)
    total_ec = agg.groupby(["county", "employer_type"])["count"].transform("sum")
    national_es = agg.groupby(["employer_type", "skill"])["count"].transform("sum")
    national_et = agg.groupby("employer_type")["count"].transform("sum")

    local_share = agg["count"] / total_ec
    national_share = national_es / national_et
    agg["rca"] = np.where(national_share > 0, local_share / national_share, 0.0)
    agg["rca_binary"] = (agg["rca"] > RCA_THRESHOLD).astype(np.int8)
    agg["year"] = year

    # Write per-year output
    year_dir = os.path.join(EMP_RCA_DIR, f"year={year}")
    os.makedirs(year_dir, exist_ok=True)
    out_path = os.path.join(year_dir, "employer_rca.parquet")
    agg.to_parquet(out_path, index=False, engine="pyarrow",
                   use_dictionary=["skill", "employer_type", "skill_type"])
    log(f"    Wrote {len(agg):,} rows → {out_path}")

    # Diagnostics
    for etype in EMPLOYER_TYPES:
        e = agg[agg["employer_type"] == etype]
        rca_pos = e[e["rca_binary"] == 1]
        n_counties = rca_pos["county"].nunique()
        med_breadth = rca_pos.groupby("county")["skill"].nunique().median() if n_counties > 0 else 0
        log(f"    {etype:>12}: {n_counties:,} counties with RCA>1, "
            f"median breadth={med_breadth:.0f}")

    # Free emp, keep agg for downstream stages
    del emp
    gc.collect()
    return agg


# ============================================================
# STAGE 2: INSTITUTION-TYPE RCA (NAICS-4 level, per year)
# ============================================================

def compute_institution_rca_year(year):
    """Compute NAICS-4-level RCA within each institution type.

    For each county × naics4 cell, compute RCA of each skill relative to
    the national skill distribution within that NAICS-4 category.

    Restricted to university + federal_lab NAICS codes.
    """
    emp_path = os.path.join(SCAN_DIR, f"year={year}", "employer_skill.parquet")
    if not os.path.exists(emp_path):
        return None

    emp = pd.read_parquet(emp_path)
    # Filter to institution NAICS codes
    emp = emp[emp["naics4"].isin(INSTITUTION_NAICS4)].copy()
    if len(emp) == 0:
        log(f"    No institution-type postings in {year}")
        return None

    # Aggregate to (county, naics4, skill, skill_type, employer_type)
    agg = (emp.groupby(["county", "naics4", "skill", "skill_type", "employer_type"],
                       observed=True)["count"].sum().reset_index())
    agg = agg[agg["count"] >= MIN_COUNT].copy()

    if len(agg) == 0:
        return None

    # RCA denominators (NAICS-4 specific)
    total_cn = agg.groupby(["county", "naics4"])["count"].transform("sum")
    national_ns = agg.groupby(["naics4", "skill"])["count"].transform("sum")
    national_n = agg.groupby("naics4")["count"].transform("sum")

    local_share = agg["count"] / total_cn
    national_share = national_ns / national_n
    agg["rca"] = np.where(national_share > 0, local_share / national_share, 0.0)
    agg["rca_binary"] = (agg["rca"] > RCA_THRESHOLD).astype(np.int8)
    agg["year"] = year

    year_dir = os.path.join(INST_RCA_DIR, f"year={year}")
    os.makedirs(year_dir, exist_ok=True)
    out_path = os.path.join(year_dir, "institution_type_rca.parquet")
    agg.to_parquet(out_path, index=False, engine="pyarrow",
                   use_dictionary=["skill", "naics4", "employer_type", "skill_type"])
    log(f"    Institution RCA: {len(agg):,} rows → {out_path}")

    # Summary by NAICS-4
    for n4 in sorted(agg["naics4"].unique()):
        sub = agg[agg["naics4"] == n4]
        n_counties = sub["county"].nunique()
        rca_pos = sub[sub["rca_binary"] == 1]
        med_breadth = rca_pos.groupby("county")["skill"].nunique().median() if len(rca_pos) > 0 else 0
        log(f"      NAICS {n4}: {n_counties:,} counties, median RCA breadth={med_breadth:.0f}")

    del emp
    gc.collect()
    return agg


# ============================================================
# STAGE 3: EMPLOYER-TYPE DYNAMICS
# ============================================================

def compute_employer_dynamics():
    """Year-over-year dynamics per employer type.

    Reads per-year employer_rca outputs and computes:
      - churning_entries/exits/net (RCA set differences)
      - cosine_distance (on skill frequency vectors within employer type)
      - n_rca_skills (breadth)

    Returns DataFrame: (county, employer_type, year, ...)
    """
    log("Computing employer-type dynamics...")
    prev_by_etype = {}  # etype → {county → (rca_set, freq_dict)}
    all_rows = []

    for year in YEARS:
        year_dir = os.path.join(EMP_RCA_DIR, f"year={year}")
        fp = os.path.join(year_dir, "employer_rca.parquet")
        if not os.path.exists(fp):
            prev_by_etype = {}
            continue

        df = pd.read_parquet(fp)

        curr_by_etype = {}
        for etype in EMPLOYER_TYPES:
            e = df[df["employer_type"] == etype]
            if len(e) == 0:
                continue

            rca_sets = (e[e["rca_binary"] == 1]
                        .groupby("county")["skill"].apply(set).to_dict())

            # Build frequency dict per county (for cosine)
            freq = {}
            for county, grp in e.groupby("county"):
                freq[county] = dict(zip(grp["skill"], grp["count"]))

            curr_by_etype[etype] = (rca_sets, freq)

            # Compute breadth for all counties (not just dynamics)
            for county, skills in rca_sets.items():
                all_rows.append({
                    "county": county, "year": year, "employer_type": etype,
                    "n_rca_skills": len(skills),
                    "churning_entries": np.nan,
                    "churning_exits": np.nan,
                    "churning_net": np.nan,
                    "cosine_distance": np.nan,
                })

        # Compute dynamics vs prior year
        for etype in EMPLOYER_TYPES:
            if etype not in curr_by_etype or etype not in prev_by_etype:
                continue
            curr_rca, curr_freq = curr_by_etype[etype]
            prev_rca, prev_freq = prev_by_etype[etype]

            all_counties = set(curr_rca.keys()) | set(prev_rca.keys())
            for county in all_counties:
                s_prev = prev_rca.get(county, set())
                s_curr = curr_rca.get(county, set())
                entries = len(s_curr - s_prev)
                exits = len(s_prev - s_curr)

                # Cosine distance on frequency vectors
                f_prev = prev_freq.get(county, {})
                f_curr = curr_freq.get(county, {})
                skills_union = sorted(set(f_prev.keys()) | set(f_curr.keys()))
                if skills_union:
                    vp = np.array([f_prev.get(s, 0) for s in skills_union], dtype=np.float64)
                    vc = np.array([f_curr.get(s, 0) for s in skills_union], dtype=np.float64)
                    cs = cosine_sim(vp, vc)
                    cos_dist = 1 - cs if not np.isnan(cs) else np.nan
                else:
                    cos_dist = np.nan

                # Find and update the all_rows entry for this (county, year, etype)
                # (less efficient but simpler than rebuilding the structure)
                all_rows.append({
                    "county": county, "year": year, "employer_type": etype,
                    "n_rca_skills": len(s_curr),
                    "churning_entries": entries,
                    "churning_exits": exits,
                    "churning_net": entries - exits,
                    "cosine_distance": cos_dist,
                })

            log(f"    {year} {etype:>12}: dynamics for {len(all_counties):,} counties")

        prev_by_etype = curr_by_etype
        del df
        gc.collect()

    dyn = pd.DataFrame(all_rows)
    # Drop the NaN-dynamics placeholders where we also have real dynamics rows
    # Keep the non-NaN one when duplicates exist (dynamics overwrites breadth-only)
    dyn = dyn.sort_values(["county", "year", "employer_type", "churning_entries"],
                          na_position="first")
    dyn = dyn.drop_duplicates(["county", "year", "employer_type"], keep="last")
    return dyn.reset_index(drop=True)


# ============================================================
# STAGE 4: UPDATE COUNTY_YEAR_PANEL
# ============================================================

def update_county_year_panel(emp_dynamics):
    """Merge new columns into county_year_panel.parquet.

    Adds:
      - share_remote, share_hybrid, share_onsite (from fixed remote counts)
      - {etype}_n_rca_skills, {etype}_churning_net, {etype}_cosine_distance
    """
    log("Updating county_year_panel...")

    panel_path = os.path.join(PANEL_DIR, "county_year_panel.parquet")
    panel = pd.read_parquet(panel_path)
    log(f"  Loaded existing panel: {panel.shape[0]:,} rows × {panel.shape[1]} cols")

    # Need to pull updated remote columns from the v2 panel_stats
    # (the existing panel has the bugged n_remote from v1)
    ps_frames = []
    for year in YEARS:
        fp = os.path.join(SCAN_DIR, f"year={year}", "panel_stats.parquet")
        if os.path.exists(fp):
            ps = pd.read_parquet(fp)
            ps["year"] = year
            ps_frames.append(ps)
    ps_new = pd.concat(ps_frames, ignore_index=True)

    # Drop bugged columns from existing panel, use v2 panel_stats values
    # Columns to update: n_remote, n_hybrid, n_onsite, n_remote_other
    for col in ["n_remote", "n_hybrid", "n_onsite", "n_remote_other"]:
        if col in panel.columns:
            panel = panel.drop(columns=col)

    panel = panel.merge(
        ps_new[["county", "year", "n_remote", "n_hybrid", "n_onsite", "n_remote_other"]],
        on=["county", "year"], how="left"
    )

    # Compute shares
    total = panel["total_postings"].replace(0, np.nan)
    panel["share_remote"] = panel["n_remote"] / total
    panel["share_hybrid"] = panel["n_hybrid"] / total
    panel["share_onsite"] = panel["n_onsite"] / total

    # Add employer-type measures (pivot emp_dynamics wide)
    for etype in EMPLOYER_TYPES:
        sub = emp_dynamics[emp_dynamics["employer_type"] == etype][
            ["county", "year", "n_rca_skills", "churning_entries",
             "churning_exits", "churning_net", "cosine_distance"]
        ].copy()
        # Short prefix: use first 4 chars of etype (same convention as v1)
        prefix = etype[:4] if etype != "federal_lab" else "fede"
        sub = sub.rename(columns={
            "n_rca_skills": f"{prefix}_n_rca_skills",
            "churning_entries": f"{prefix}_churning_entries",
            "churning_exits": f"{prefix}_churning_exits",
            "churning_net": f"{prefix}_churning_net",
            "cosine_distance": f"{prefix}_cosine_distance",
        })
        panel = panel.merge(sub, on=["county", "year"], how="left")

    out_path = os.path.join(PANEL_DIR, "county_year_panel.parquet")
    panel.to_parquet(out_path, index=False, engine="pyarrow")
    log(f"  Wrote updated panel: {panel.shape[0]:,} rows × {panel.shape[1]} cols → {out_path}")

    return panel


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 60)
    log("Phase B v2: Employer RCA + Institution RCA + Dynamics")
    log("=" * 60)

    os.makedirs(EMP_RCA_DIR, exist_ok=True)
    os.makedirs(INST_RCA_DIR, exist_ok=True)

    # Stage 1: Employer-type RCA per year
    log("")
    log("Stage 1: Employer-type RCA per year")
    log("-" * 60)
    for year in YEARS:
        compute_employer_rca_year(year)

    # Stage 2: Institution-type RCA per year
    log("")
    log("Stage 2: Institution-type RCA (NAICS-4 level)")
    log("-" * 60)
    for year in YEARS:
        compute_institution_rca_year(year)

    # Stage 3: Employer-type dynamics
    log("")
    log("Stage 3: Employer-type dynamics (year-over-year)")
    log("-" * 60)
    dyn = compute_employer_dynamics()
    dyn_path = os.path.join(PANEL_DIR, "employer_dynamics.parquet")
    dyn.to_parquet(dyn_path, index=False, engine="pyarrow")
    log(f"  Wrote {len(dyn):,} rows → {dyn_path}")

    # Stage 4: Update county_year_panel
    log("")
    log("Stage 4: Update county_year_panel with new columns")
    log("-" * 60)
    update_county_year_panel(dyn)

    log("")
    log("=" * 60)
    log("Phase B v2 complete.")
    log("=" * 60)


if __name__ == "__main__":
    main()
