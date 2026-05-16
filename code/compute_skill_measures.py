#!/usr/bin/env python3
"""
Phase B: Compute Skill Measures
================================

Reads Phase A checkpoints and computes the full battery of skill-space measures.

Measures computed:
  1. RCA per (county, year, skill) + ubiquity per skill
  2. Skill relatedness matrix (Hidalgo & Hausmann 2007 proximity, per year)
  3. Skill density & relatedness density (Balland et al. 2019)
  4. Skill coherence (Neffke et al. 2011)
  5. Complexity: ECI (method of reflections) + fitness-complexity (Tacchella 2012)
  6. Skill space position (average network centrality)
  7. Skill dynamics: churning, entry/exit relatedness, cosine distance
  8. Employer-type similarity: cosine, Jaccard, Hidalgo proximity,
     weighted RCA overlap, skill gap — decomposed by skill type

Inputs:
  intermediate/scan/year=YYYY/{skill_counts,employer_skill,panel_stats}.parquet

Outputs:
  panels/county_skill_year.parquet   (~50-100M rows)
  panels/county_year_panel.parquet   (~46,500 rows, ~100+ columns)
  rca/skill_relatedness.parquet      (sparse pairwise, per year)

Expected runtime: 30-60 min on Sol.
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
# contains ./processed (Phase A's output root).
BASE_DIR = os.environ.get("LIGHTCAST_DATA_DIR", "./processed")
SCAN_DIR = os.path.join(BASE_DIR, "intermediate/scan")
PANEL_DIR = os.path.join(BASE_DIR, "panels")
RCA_DIR = os.path.join(BASE_DIR, "rca")

YEARS = list(range(2010, 2025))

EMPLOYER_TYPES = ["corporate", "university", "federal_lab",
                  "government", "staffing", "unclassified"]

# Pairs for employer-type similarity. All 6 unordered pairs over the four
# released entity types (corporate, university, federal/public lab, government).
# Naming convention follows {type_a[:4]}_{type_b[:4]}:
#   univ_corp, fede_corp, gove_corp, univ_fede, univ_gove, fede_gove
EMPLOYER_PAIRS = [
    ("university", "corporate"),
    ("federal_lab", "corporate"),
    ("government", "corporate"),
    ("university", "federal_lab"),
    ("university", "government"),
    ("federal_lab", "government"),
]

SKILL_TYPES = ["specialized", "software", "common"]

# Fitness-complexity iterations. ECI uses spectral closed form (Mealy 2019),
# not iterative method of reflections, so no iteration count is needed.
FITNESS_ITERATIONS = 50


# ============================================================
# HELPERS
# ============================================================

def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


def cosine_sim(a, b):
    """Cosine similarity between two vectors. Returns NaN if either is zero."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return np.nan
    return np.dot(a, b) / (norm_a * norm_b)


def safe_div(a, b, fill=0.0):
    """Element-wise a/b, filling with `fill` where b==0."""
    return np.where(b != 0, a / b, fill)


# ============================================================
# STAGE 1: LOAD CHECKPOINTS
# ============================================================

def load_checkpoints():
    """Load skill_counts and panel_stats for all years.

    employer_skill is loaded per-year in the main loop to save memory
    (222M rows total — too large to hold all at once with everything else).
    """
    log("Stage 1: Loading checkpoints...")

    skill_frames = []
    panel_frames = []

    for year in YEARS:
        ydir = os.path.join(SCAN_DIR, f"year={year}")
        marker = os.path.join(ydir, "_SUCCESS")
        if not os.path.exists(marker):
            log(f"  WARN: year {year} checkpoint missing, skipping")
            continue

        sc = pd.read_parquet(os.path.join(ydir, "skill_counts.parquet"))
        sc["year"] = year
        skill_frames.append(sc)

        ps = pd.read_parquet(os.path.join(ydir, "panel_stats.parquet"))
        ps["year"] = year
        panel_frames.append(ps)

    skill_df = pd.concat(skill_frames, ignore_index=True)
    panel_df = pd.concat(panel_frames, ignore_index=True)

    log(f"  skill_counts: {len(skill_df):,} rows")
    log(f"  panel_stats: {len(panel_df):,} rows")

    return skill_df, panel_df


def load_employer_year(year):
    """Load employer_skill checkpoint for a single year."""
    ydir = os.path.join(SCAN_DIR, f"year={year}")
    fp = os.path.join(ydir, "employer_skill.parquet")
    if not os.path.exists(fp):
        return pd.DataFrame()
    ep = pd.read_parquet(fp)
    ep["year"] = year
    return ep


# ============================================================
# STAGE 2: COMPUTE RCA
# ============================================================

def compute_rca(skill_df):
    """Add RCA and ubiquity columns to skill_df.

    RCA(c,t,s) = [count(c,t,s) / total(c,t)] / [national(t,s) / national_total(t)]
    """
    log("Stage 2: Computing RCA...")

    total_ct = skill_df.groupby(["county", "year"])["count"].transform("sum")
    national_ts = skill_df.groupby(["year", "skill"])["count"].transform("sum")
    national_t = skill_df.groupby("year")["count"].transform("sum")

    share_local = skill_df["count"] / total_ct
    share_national = national_ts / national_t

    skill_df["rca"] = safe_div(share_local, share_national, fill=0.0)
    skill_df["rca_binary"] = (skill_df["rca"] > 1).astype(np.int8)

    # Ubiquity: how many counties have RCA > 1 for each (year, skill)
    ubiq = (skill_df[skill_df["rca_binary"] == 1]
            .groupby(["year", "skill"])["county"]
            .nunique()
            .reset_index(name="ubiquity"))
    skill_df = skill_df.merge(ubiq, on=["year", "skill"], how="left")
    skill_df["ubiquity"] = skill_df["ubiquity"].fillna(0).astype(int)

    log(f"  RCA > 1 entries: {skill_df['rca_binary'].sum():,}")
    log(f"  Distinct skills with RCA > 1 somewhere: "
        f"{skill_df.loc[skill_df['rca_binary']==1, 'skill'].nunique():,}")

    return skill_df


# ============================================================
# STAGE 3: SKILL RELATEDNESS MATRIX (per year)
# ============================================================

def compute_relatedness_year(skill_df_year):
    """Compute Hidalgo & Hausmann (2007) proximity for one year.

    phi(s_i, s_j) = min(P(RCA>1 for s_j | RCA>1 for s_i),
                        P(RCA>1 for s_i | RCA>1 for s_j))

    Returns:
      phi: ndarray (n_active, n_active) — relatedness matrix
      active_skills: list of skill names (index into phi)
    """
    rca_pos = skill_df_year[skill_df_year["rca_binary"] == 1]

    # Active skills: those with RCA > 1 in at least 2 counties
    skill_ubiq = rca_pos.groupby("skill")["county"].nunique()
    active_skills = sorted(skill_ubiq[skill_ubiq >= 2].index.tolist())

    if len(active_skills) < 2:
        return None, active_skills

    # Build binary matrix M: (counties, active_skills)
    counties = sorted(rca_pos["county"].unique())
    county_idx = {c: i for i, c in enumerate(counties)}
    skill_idx = {s: i for i, s in enumerate(active_skills)}

    n_c = len(counties)
    n_s = len(active_skills)

    # Vectorized M construction — no iterrows
    rca_active = rca_pos[rca_pos["skill"].isin(skill_idx)]
    ci_arr = rca_active["county"].map(county_idx).values
    si_arr = rca_active["skill"].map(skill_idx).values
    valid = ~(np.isnan(ci_arr) | np.isnan(si_arr)) if hasattr(ci_arr, 'dtype') else np.ones(len(ci_arr), dtype=bool)
    M = np.zeros((n_c, n_s), dtype=np.float32)
    M[ci_arr[valid].astype(int), si_arr[valid].astype(int)] = 1.0

    # Co-occurrence: joint[i,j] = number of counties where both s_i and s_j have RCA > 1
    joint = M.T @ M  # (n_s, n_s)
    marginals = np.diag(joint).copy()  # (n_s,)

    # phi(i,j) = min(joint[i,j]/marginal[i], joint[i,j]/marginal[j])
    marg_i = marginals[:, np.newaxis]  # (n_s, 1)
    marg_j = marginals[np.newaxis, :]  # (1, n_s)

    with np.errstate(divide="ignore", invalid="ignore"):
        cond_ij = joint / marg_i  # P(j|i)
        cond_ji = joint / marg_j  # P(i|j)

    phi = np.minimum(cond_ij, cond_ji)
    np.fill_diagonal(phi, 0.0)  # no self-relatedness
    phi = np.nan_to_num(phi, 0.0)

    return phi, active_skills


def relatedness_to_sparse_df(phi, active_skills, year, min_phi=0.05):
    """Convert relatedness matrix to sparse DataFrame for storage."""
    rows = []
    n = len(active_skills)
    for i in range(n):
        for j in range(i + 1, n):
            if phi[i, j] >= min_phi:
                rows.append({
                    "year": year,
                    "skill_i": active_skills[i],
                    "skill_j": active_skills[j],
                    "phi": round(float(phi[i, j]), 4),
                })
    return pd.DataFrame(rows)


# ============================================================
# STAGE 4: COUNTY-YEAR MEASURES (per year)
# ============================================================

def compute_county_measures(year, skill_year, phi, active_skills, skill_idx_map):
    """Compute all county-level measures for one year.

    Returns a list of dicts, one per county.
    """
    counties = sorted(skill_year["county"].unique())
    n_s = len(active_skills)
    has_phi = phi is not None and n_s >= 2

    # Precompute: degree centrality of each skill in the relatedness network
    if has_phi:
        degree = phi.sum(axis=1) / max(n_s - 1, 1)
    else:
        degree = np.zeros(0)

    # Build RCA binary matrix for ECI/fitness
    if has_phi:
        county_list = sorted(skill_year["county"].unique())
        county_idx = {c: i for i, c in enumerate(county_list)}
        n_c = len(county_list)

        M = np.zeros((n_c, n_s), dtype=np.float32)
        rca_pos = skill_year[skill_year["rca_binary"] == 1]
        rca_active = rca_pos[rca_pos["skill"].isin(skill_idx_map)]
        ci_arr = rca_active["county"].map(county_idx).dropna().astype(int)
        si_arr = rca_active["skill"].map(skill_idx_map).loc[ci_arr.index].astype(int)
        M[ci_arr.values, si_arr.values] = 1.0

        # Diversification and ubiquity
        k_c = M.sum(axis=1)  # (n_c,)
        k_s = M.sum(axis=0)  # (n_s,)

        # ECI: method of reflections
        eci_scores = compute_eci(M, k_c, k_s)

        # Fitness-complexity
        fitness_scores, complexity_scores = compute_fitness_complexity(M)

        # Density matrix: for each (county, skill), average relatedness to county's RCA portfolio
        phi_row_sums = phi.sum(axis=1)  # (n_s,)
        # density_matrix[c, s] = sum(phi[s, s'] * M[c, s']) / phi_row_sums[s]
        numerator = M @ phi  # (n_c, n_s)
        with np.errstate(divide="ignore", invalid="ignore"):
            density_matrix = numerator / phi_row_sums[np.newaxis, :]
        density_matrix = np.nan_to_num(density_matrix, 0.0)
    else:
        county_list = counties
        county_idx = {c: i for i, c in enumerate(county_list)}
        n_c = len(county_list)
        M = np.zeros((n_c, 0))
        k_c = np.zeros(n_c)
        eci_scores = np.full(n_c, np.nan)
        fitness_scores = np.full(n_c, np.nan)
        density_matrix = np.zeros((n_c, 0))

    # Pre-compute grouped aggregates (avoids O(n) filter per county)
    rca_ubiq_avg = (skill_year[skill_year["rca_binary"] == 1]
                    .groupby("county")["ubiquity"].mean())

    county_total = skill_year.groupby("county")["count"].sum()
    county_ndistinct = skill_year.groupby("county")["skill"].nunique()

    # HHI and entropy per county
    def _hhi_entropy(group):
        total = group["count"].sum()
        if total == 0:
            return pd.Series({"skill_hhi": np.nan, "skill_entropy": np.nan})
        freqs = group["count"].values / total
        hhi = float((freqs ** 2).sum())
        nonzero = freqs[freqs > 0]
        entropy = float(-np.sum(nonzero * np.log2(nonzero)))
        return pd.Series({"skill_hhi": hhi, "skill_entropy": entropy})

    hhi_ent = skill_year.groupby("county").apply(_hhi_entropy)

    # Share by skill type
    type_sums = skill_year.groupby(["county", "skill_type"])["count"].sum().unstack(fill_value=0)
    for st in SKILL_TYPES:
        if st not in type_sums.columns:
            type_sums[st] = 0

    # Build per-county results
    results = []
    for county in counties:
        ci = county_idx.get(county)
        if ci is None:
            continue

        rca_vec = M[ci] if has_phi else np.array([])
        n_rca = int(rca_vec.sum()) if has_phi else 0
        rca_mask = rca_vec > 0

        row = {"county": county, "year": year}

        row["n_rca_skills"] = n_rca
        row["avg_ubiquity"] = rca_ubiq_avg.get(county, np.nan)

        total_mentions = county_total.get(county, 0)
        row["n_distinct_skills"] = county_ndistinct.get(county, 0)

        if county in hhi_ent.index:
            row["skill_hhi"] = hhi_ent.loc[county, "skill_hhi"]
            row["skill_entropy"] = hhi_ent.loc[county, "skill_entropy"]
        else:
            row["skill_hhi"] = np.nan
            row["skill_entropy"] = np.nan

        for stype in SKILL_TYPES:
            st_sum = type_sums.loc[county, stype] if county in type_sums.index else 0
            row[f"share_{stype}"] = st_sum / total_mentions if total_mentions > 0 else np.nan

        row["eci"] = float(eci_scores[ci]) if has_phi else np.nan
        row["fitness"] = float(fitness_scores[ci]) if has_phi else np.nan

        if has_phi and n_rca > 0 and n_rca < n_s:
            non_rca_mask = ~rca_mask
            row["skill_density"] = float(density_matrix[ci, non_rca_mask].mean())
        else:
            row["skill_density"] = np.nan

        if has_phi and n_rca >= 2:
            rca_indices = np.where(rca_mask)[0]
            sub_phi = phi[np.ix_(rca_indices, rca_indices)]
            n_pairs = n_rca * (n_rca - 1)
            row["skill_coherence"] = float(sub_phi.sum() / n_pairs) if n_pairs > 0 else np.nan
        else:
            row["skill_coherence"] = np.nan

        if has_phi and n_rca > 0:
            row["avg_centrality"] = float(degree[rca_mask].mean())
        else:
            row["avg_centrality"] = np.nan

        results.append(row)

    return results


def compute_eci(M, k_c, k_s):
    """Economic Complexity Index via method of reflections.

    M: (n_c, n_s) binary RCA matrix
    k_c: (n_c,) diversification
    k_s: (n_s,) ubiquity

    Returns: (n_c,) ECI scores (standardized)
    """
    n_c, n_s = M.shape
    if n_c < 2 or n_s < 2:
        return np.full(n_c, np.nan)

    # Build the M_tilde matrix
    with np.errstate(divide="ignore", invalid="ignore"):
        kc_inv = safe_div(1.0, k_c)
        ks_inv = safe_div(1.0, k_s)

    # M_cc' = (1/k_c) * sum_s M[c,s] * M[c',s] / k_s
    # This is: diag(1/k_c) @ M @ diag(1/k_s) @ M^T
    M_tilde = np.diag(kc_inv) @ M @ np.diag(ks_inv) @ M.T

    # ECI = eigenvector for second-largest eigenvalue
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(M_tilde)
        # eigh returns in ascending order; second-largest = index -2
        eci_raw = eigenvectors[:, -2]
        # Standardize
        std = eci_raw.std()
        if std > 0:
            eci = (eci_raw - eci_raw.mean()) / std
        else:
            eci = np.full(n_c, 0.0)
        # Sign convention: positive correlation with diversification
        if np.corrcoef(eci, k_c)[0, 1] < 0:
            eci = -eci
        return eci
    except np.linalg.LinAlgError:
        return np.full(n_c, np.nan)


def compute_fitness_complexity(M, n_iter=FITNESS_ITERATIONS):
    """Tacchella et al. (2012) fitness-complexity algorithm.

    Returns: (fitness, complexity) arrays
    """
    n_c, n_s = M.shape
    if n_c < 2 or n_s < 2:
        return np.full(n_c, np.nan), np.full(n_s, np.nan)

    F = np.ones(n_c)
    Q = np.ones(n_s)

    for _ in range(n_iter):
        F_new = M @ Q
        with np.errstate(divide="ignore", invalid="ignore"):
            Q_tilde = safe_div(1.0, M.T @ safe_div(1.0, F))
        # Normalize
        F_mean = F_new.mean()
        Q_mean = Q_tilde.mean()
        F = F_new / F_mean if F_mean > 0 else F_new
        Q = Q_tilde / Q_mean if Q_mean > 0 else Q_tilde

    return F, Q


# ============================================================
# STAGE 5: EMPLOYER-TYPE SIMILARITY (per year)
# ============================================================

def compute_employer_similarity(year, emp_year, phi, active_skills, skill_idx_map):
    """Compute employer-type similarity for all pairs in one year.

    Optimized: pre-groups by county, uses numpy indexing for Hidalgo proximity.
    Returns dict of county → {metric columns}.
    """
    if len(emp_year) == 0:
        return {}

    # The Phase A employer_skill.parquet is keyed by
    # (county, employer_type, naics2, naics4, skill, skill_type). For RCA and
    # the pairwise similarity work below we need data at (county, employer_type,
    # skill, skill_type) — sum across the naics2/naics4 sub-rows so that the
    # later set_index("skill") step does not produce a duplicate-labeled index.
    # This step is a no-op for entity types with a single naics4 per skill and
    # corrects the RCA denominator for entity types that span multiple naics4.
    emp_year = (
        emp_year
        .groupby(["county", "employer_type", "skill", "skill_type", "year"],
                 as_index=False, observed=True)
        .agg({"count": "sum"})
    )

    # Build employer-type-specific RCA
    total_ec = emp_year.groupby(["county", "employer_type"])["count"].transform("sum")
    national_es = emp_year.groupby(["year", "employer_type", "skill"])["count"].transform("sum")
    national_et = emp_year.groupby(["year", "employer_type"])["count"].transform("sum")

    share_local = safe_div(emp_year["count"].values, total_ec.values)
    share_national = safe_div(national_es.values, national_et.values)
    emp_year = emp_year.copy()
    emp_year["rca_e"] = safe_div(share_local, share_national)
    emp_year["rca_e_binary"] = (emp_year["rca_e"] > 1).astype(np.int8)

    # Pre-group by (county, employer_type) — O(1) lookup per county
    grouped = {}
    for (county, etype), grp in emp_year.groupby(["county", "employer_type"]):
        grouped[(county, etype)] = grp.set_index("skill")

    # All metric column names for NaN filling
    nan_cols = []
    for type_a, type_b in EMPLOYER_PAIRS:
        prefix = f"{type_a[:4]}_{type_b[:4]}"
        for metric in ["cosine", "jaccard", "hidalgo", "rca_overlap",
                        "gap_count", "gap_relatedness"]:
            nan_cols.append(f"{metric}_{prefix}")
            for stype in SKILL_TYPES:
                nan_cols.append(f"{metric}_{prefix}_{stype}")

    counties = sorted(emp_year["county"].unique())
    results = {}

    for county in counties:
        row = {}

        for type_a, type_b in EMPLOYER_PAIRS:
            a_idx = grouped.get((county, type_a))
            b_idx = grouped.get((county, type_b))
            prefix = f"{type_a[:4]}_{type_b[:4]}"

            if a_idx is None or b_idx is None or len(a_idx) == 0 or len(b_idx) == 0:
                for col in nan_cols:
                    if col.startswith(("cosine_" + prefix, "jaccard_" + prefix,
                                       "hidalgo_" + prefix, "rca_overlap_" + prefix,
                                       "gap_count_" + prefix, "gap_relatedness_" + prefix)):
                        row[col] = np.nan
                continue

            all_skills_ab = sorted(set(a_idx.index) | set(b_idx.index))
            skill_type_map = {}
            for df_idx in [a_idx, b_idx]:
                if "skill_type" in df_idx.columns:
                    for s, st in zip(df_idx.index, df_idx["skill_type"]):
                        if s not in skill_type_map:
                            skill_type_map[s] = st

            a_count = a_idx["count"].reindex(all_skills_ab, fill_value=0)
            b_count = b_idx["count"].reindex(all_skills_ab, fill_value=0)
            a_rca_s = a_idx["rca_e"].reindex(all_skills_ab, fill_value=0.0)
            b_rca_s = b_idx["rca_e"].reindex(all_skills_ab, fill_value=0.0)

            for scope, scope_skills in [("", all_skills_ab)] + [
                (f"_{st}", [s for s in all_skills_ab
                            if skill_type_map.get(s) == st])
                for st in SKILL_TYPES
            ]:
                if not scope_skills:
                    for metric in ["cosine", "jaccard", "hidalgo",
                                   "rca_overlap", "gap_count", "gap_relatedness"]:
                        row[f"{metric}_{prefix}{scope}"] = np.nan
                    continue

                vec_a = a_count.loc[scope_skills].values.astype(np.float64)
                vec_b = b_count.loc[scope_skills].values.astype(np.float64)

                row[f"cosine_{prefix}{scope}"] = cosine_sim(vec_a, vec_b)

                rca_a = a_rca_s.loc[scope_skills].values
                rca_b = b_rca_s.loc[scope_skills].values
                mask_a = rca_a > 1
                mask_b = rca_b > 1
                union_n = int((mask_a | mask_b).sum())
                inter_n = int((mask_a & mask_b).sum())
                row[f"jaccard_{prefix}{scope}"] = inter_n / union_n if union_n > 0 else np.nan

                if mask_a.any():
                    row[f"rca_overlap_{prefix}{scope}"] = float(rca_b[mask_a].mean())
                else:
                    row[f"rca_overlap_{prefix}{scope}"] = np.nan

                # Hidalgo proximity via numpy fancy indexing
                if phi is not None:
                    skills_a_rca = [s for s, m in zip(scope_skills, mask_a) if m]
                    skills_b_rca = [s for s, m in zip(scope_skills, mask_b) if m]
                    idx_a = np.array([skill_idx_map[s] for s in skills_a_rca
                                      if s in skill_idx_map], dtype=int)
                    idx_b = np.array([skill_idx_map[s] for s in skills_b_rca
                                      if s in skill_idx_map], dtype=int)
                    if len(idx_a) > 0 and len(idx_b) > 0:
                        sub = phi[np.ix_(idx_a, idx_b)]
                        row[f"hidalgo_{prefix}{scope}"] = float(np.nanmean(sub))
                    else:
                        row[f"hidalgo_{prefix}{scope}"] = np.nan
                else:
                    row[f"hidalgo_{prefix}{scope}"] = np.nan

                # Skill gap
                gap_mask = mask_a & ~mask_b
                row[f"gap_count_{prefix}{scope}"] = int(gap_mask.sum())
                if gap_mask.any() and phi is not None:
                    gap_skills = [s for s, m in zip(scope_skills, gap_mask) if m]
                    idx_gap = np.array([skill_idx_map[s] for s in gap_skills
                                        if s in skill_idx_map], dtype=int)
                    idx_b_rca = np.array([skill_idx_map[s] for s in skills_b_rca
                                          if s in skill_idx_map], dtype=int)
                    if len(idx_gap) > 0 and len(idx_b_rca) > 0:
                        sub = phi[np.ix_(idx_gap, idx_b_rca)]
                        row[f"gap_relatedness_{prefix}{scope}"] = float(np.nanmean(sub))
                    else:
                        row[f"gap_relatedness_{prefix}{scope}"] = np.nan
                else:
                    row[f"gap_relatedness_{prefix}{scope}"] = np.nan

        results[county] = row

    return results


# ============================================================
# STAGE 6: SKILL DYNAMICS (year-over-year)
# ============================================================

def compute_dynamics(skill_df):
    """Compute year-over-year dynamics for each county.

    Returns DataFrame with columns:
      county, year, churning_entries, churning_exits, churning_net,
      skill_cosine_distance
    """
    log("Stage 6: Computing skill dynamics...")

    years_sorted = sorted(skill_df["year"].unique())
    dyn_rows = []

    for i in range(1, len(years_sorted)):
        year_prev = years_sorted[i - 1]
        year_curr = years_sorted[i]

        prev = skill_df[skill_df["year"] == year_prev]
        curr = skill_df[skill_df["year"] == year_curr]

        # RCA churning: vectorized set operations via merge
        prev_rca = (prev[prev["rca_binary"] == 1][["county", "skill"]]
                    .assign(_prev=1))
        curr_rca = (curr[curr["rca_binary"] == 1][["county", "skill"]]
                    .assign(_curr=1))
        merged_rca = prev_rca.merge(curr_rca, on=["county", "skill"], how="outer")
        merged_rca["_prev"] = merged_rca["_prev"].fillna(0).astype(int)
        merged_rca["_curr"] = merged_rca["_curr"].fillna(0).astype(int)
        merged_rca["is_entry"] = (merged_rca["_prev"] == 0) & (merged_rca["_curr"] == 1)
        merged_rca["is_exit"] = (merged_rca["_prev"] == 1) & (merged_rca["_curr"] == 0)

        churning = merged_rca.groupby("county").agg(
            churning_entries=("is_entry", "sum"),
            churning_exits=("is_exit", "sum"),
        ).reset_index()
        churning["churning_net"] = churning["churning_entries"] - churning["churning_exits"]
        churning["year"] = year_curr

        # Cosine distance: vectorized via pivot + sparse dot product
        prev_wide = prev[["county", "skill", "count"]].rename(columns={"count": "prev_count"})
        curr_wide = curr[["county", "skill", "count"]].rename(columns={"count": "curr_count"})
        merged_freq = prev_wide.merge(curr_wide, on=["county", "skill"], how="outer")
        merged_freq["prev_count"] = merged_freq["prev_count"].fillna(0)
        merged_freq["curr_count"] = merged_freq["curr_count"].fillna(0)

        # Per-county dot product, norms
        merged_freq["dot"] = merged_freq["prev_count"] * merged_freq["curr_count"]
        merged_freq["prev_sq"] = merged_freq["prev_count"] ** 2
        merged_freq["curr_sq"] = merged_freq["curr_count"] ** 2

        cos_agg = merged_freq.groupby("county").agg(
            dot_sum=("dot", "sum"),
            prev_norm_sq=("prev_sq", "sum"),
            curr_norm_sq=("curr_sq", "sum"),
        ).reset_index()
        cos_agg["prev_norm"] = np.sqrt(cos_agg["prev_norm_sq"])
        cos_agg["curr_norm"] = np.sqrt(cos_agg["curr_norm_sq"])
        denom = cos_agg["prev_norm"] * cos_agg["curr_norm"]
        cos_agg["skill_cosine_distance"] = np.where(
            denom > 0, 1.0 - cos_agg["dot_sum"] / denom, np.nan
        )
        cos_agg["year"] = year_curr

        # Merge churning + cosine
        year_dyn = churning.merge(
            cos_agg[["county", "year", "skill_cosine_distance"]],
            on=["county", "year"], how="outer"
        )
        dyn_rows.append(year_dyn)

        log(f"    {year_prev}→{year_curr}: {len(year_dyn):,} counties")

    result = pd.concat(dyn_rows, ignore_index=True) if dyn_rows else pd.DataFrame()
    log(f"  Dynamics computed for {len(result):,} county-years")
    return result


# ============================================================
# STAGE 7: MERGE EMPLOYER COUNTS INTO SKILL TABLE
# ============================================================

def add_employer_counts(skill_df):
    """Pivot employer-skill counts and merge into skill_df, loading per-year."""
    log("Stage 7: Merging employer counts into skill table...")

    all_emp = []
    for year in YEARS:
        emp_year = load_employer_year(year)
        if len(emp_year) > 0:
            all_emp.append(emp_year[["county", "year", "employer_type", "skill", "count"]])
    if not all_emp:
        return skill_df
    emp_df = pd.concat(all_emp, ignore_index=True)
    del all_emp

    for etype in EMPLOYER_TYPES:
        sub = emp_df[emp_df["employer_type"] == etype][["county", "year", "skill", "count"]]
        sub = sub.rename(columns={"count": f"n_{etype}"})
        skill_df = skill_df.merge(sub, on=["county", "year", "skill"], how="left")
        skill_df[f"n_{etype}"] = skill_df[f"n_{etype}"].fillna(0).astype(int)

    del emp_df
    gc.collect()
    return skill_df


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 60)
    log("Phase B: Compute Skill Measures")
    log("=" * 60)
    log("")

    os.makedirs(PANEL_DIR, exist_ok=True)
    os.makedirs(RCA_DIR, exist_ok=True)

    # ---- Stage 1: Load ----
    skill_df, panel_df = load_checkpoints()

    # ---- Stage 2: RCA ----
    skill_df = compute_rca(skill_df)

    # Build skill_type lookup once (small — one row per unique skill)
    skill_type_lookup = (skill_df[["skill", "skill_type"]]
                         .drop_duplicates("skill")
                         .set_index("skill")["skill_type"])

    # ---- Stages 3-5: Per-year relatedness + county measures + employer sim ----
    # Write per-year intermediates to disk to avoid memory accumulation
    # (relatedness alone is ~160M pairs/year × 15 years = too large for RAM)
    log("Stages 3-5: Per-year relatedness, county measures, employer similarity...")

    stage_dir = os.path.join(BASE_DIR, "intermediate/stage35")
    os.makedirs(stage_dir, exist_ok=True)

    for year in YEARS:
        year_skill = skill_df[skill_df["year"] == year]

        if len(year_skill) == 0:
            log(f"  Year {year}: no data, skipping")
            continue

        log(f"  Year {year}: {len(year_skill):,} skill rows, "
            f"{year_skill['rca_binary'].sum():,} RCA>1")

        # Stage 3: Relatedness matrix
        phi, active_skills = compute_relatedness_year(year_skill)
        skill_idx_map = {s: i for i, s in enumerate(active_skills)}

        if phi is not None:
            rel_df = relatedness_to_sparse_df(phi, active_skills, year)
            rel_path = os.path.join(RCA_DIR, f"skill_relatedness_{year}.parquet")
            rel_df.to_parquet(rel_path, index=False, engine="pyarrow")
            log(f"    Relatedness: {len(active_skills)} active skills, "
                f"{len(rel_df):,} pairs → {rel_path}")
            del rel_df

        # Stage 4: County measures
        cy = compute_county_measures(year, year_skill, phi,
                                     active_skills, skill_idx_map)
        cy_df = pd.DataFrame(cy)
        cy_df.to_parquet(os.path.join(stage_dir, f"county_measures_{year}.parquet"),
                         index=False, engine="pyarrow")
        del cy, cy_df

        # Stage 5: Employer similarity — load employer data per-year
        year_emp = load_employer_year(year)
        if len(year_emp) > 0:
            year_emp["skill_type"] = (year_emp["skill"]
                                      .map(skill_type_lookup)
                                      .fillna(""))

            emp_sim = compute_employer_similarity(
                year, year_emp, phi, active_skills, skill_idx_map)
            if emp_sim:
                sim_rows = []
                for county, sim_row in emp_sim.items():
                    sim_row["county"] = county
                    sim_row["year"] = year
                    sim_rows.append(sim_row)
                sim_df = pd.DataFrame(sim_rows)
                sim_df.to_parquet(os.path.join(stage_dir, f"emp_sim_{year}.parquet"),
                                  index=False, engine="pyarrow")
                del sim_rows, sim_df
            del emp_sim

        del phi, year_skill, year_emp
        gc.collect()

    # ---- Stage 6: Dynamics ----
    dynamics_df = compute_dynamics(skill_df)

    # Write county_skill_year BEFORE assembly to free memory
    log("Writing county_skill_year...")
    out_path = os.path.join(PANEL_DIR, "county_skill_year.parquet")
    skill_df.to_parquet(out_path, index=False, engine="pyarrow")
    log(f"  {out_path}: {len(skill_df):,} rows")
    del skill_df
    gc.collect()

    # ---- Assemble county_year_panel ----
    log("Assembling county_year_panel...")

    # Read back per-year county measures and employer similarity from disk
    stage_dir = os.path.join(BASE_DIR, "intermediate/stage35")

    cm_frames = []
    for year in YEARS:
        fp = os.path.join(stage_dir, f"county_measures_{year}.parquet")
        if os.path.exists(fp):
            cm_frames.append(pd.read_parquet(fp))
    county_measures_df = pd.concat(cm_frames, ignore_index=True) if cm_frames else pd.DataFrame()
    del cm_frames

    panel_out = panel_df.merge(county_measures_df, on=["county", "year"], how="left")
    del county_measures_df

    # Add derived panel columns
    n = panel_out["total_postings"]
    panel_out["mean_skills_per_posting"] = safe_div(
        (panel_out["mention_specialized"] + panel_out["mention_software"] +
         panel_out["mention_common"]).values,
        n.values, fill=np.nan
    )
    panel_out["pct_has_skill"] = safe_div(
        panel_out["n_has_skill"].values, n.values, fill=np.nan
    ) * 100

    # Merge dynamics
    if len(dynamics_df) > 0:
        panel_out = panel_out.merge(dynamics_df, on=["county", "year"], how="left")
    del dynamics_df

    # Merge employer similarity from per-year files
    sim_frames = []
    for year in YEARS:
        fp = os.path.join(stage_dir, f"emp_sim_{year}.parquet")
        if os.path.exists(fp):
            sim_frames.append(pd.read_parquet(fp))
    if sim_frames:
        sim_df = pd.concat(sim_frames, ignore_index=True)
        panel_out = panel_out.merge(sim_df, on=["county", "year"], how="left")
        del sim_df
    del sim_frames
    gc.collect()

    # ---- Write county_year_panel ----
    log("Writing county_year_panel...")
    out_path = os.path.join(PANEL_DIR, "county_year_panel.parquet")
    panel_out.to_parquet(out_path, index=False, engine="pyarrow")
    log(f"  {out_path}: {len(panel_out):,} rows, {len(panel_out.columns)} columns")

    log("")
    log("=" * 60)
    log("Phase B complete.")
    log("=" * 60)


if __name__ == "__main__":
    main()
