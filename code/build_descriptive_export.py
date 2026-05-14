#!/usr/bin/env python3
"""
Build Descriptive Export for Nikhil
=====================================

Produces a simplified county-year panel focused on understanding how skill
and labor demand change over time. NOT anchor-firm focused.

Outputs:
  2.data/exports/county_year_panel_export.parquet
  2.data/exports/county_year_panel_export.csv
  2.data/exports/data_dictionary.csv
  4.results/tables/*.tex
  4.results/figures/*.pdf, *.png
  3.docs/Descriptive/descriptive_report.tex (+ compiled .pdf)
"""

import os
import json
import urllib.request
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px

# ============================================================
# CONFIGURATION
# ============================================================

ROOT = "/Users/ajhowel5/Claude/journal-submissions/4.Lightcast_Skills"
PANEL_PATH = f"{ROOT}/2.data/panels/county_year_panel.parquet"

EXPORT_DIR = f"{ROOT}/2.data/exports"
FIGURES_DIR = f"{ROOT}/4.results/figures"
TABLES_DIR = f"{ROOT}/4.results/tables"
DOC_DIR = f"{ROOT}/3.docs/Descriptive"

sns.set_style("whitegrid")
plt.rcParams.update({"font.family": "serif", "font.size": 10})


# ============================================================
# STEP 1: Variable subset
# ============================================================

# Grouped variable inventory: (group, [(name, type, definition), ...])
EXPORT_GROUPS = [
    ("A. Unit identifiers", [
        ("county", "string", "5-digit FIPS code"),
        ("year", "int", "Calendar year 2010-2024"),
    ]),
    ("B. Labor demand: total postings and skill mentions", [
        ("total_postings", "int", "Total unique job postings in county-year"),
        ("n_has_skill", "int", "Postings with at least one skill listed"),
        ("mention_specialized", "int", "Total mentions of specialized skills"),
        ("mention_software", "int", "Total mentions of software skills"),
        ("mention_common", "int", "Total mentions of common (soft) skills"),
        ("n_internship", "int", "Postings flagged as internships"),
    ]),
    ("C. Labor demand: posting counts by employer type", [
        ("n_corporate", "int", "Postings from corporate employers (non-univ/lab/gov/staffing)"),
        ("n_university", "int", "Postings from NAICS 6112-6117 (universities/colleges)"),
        ("n_federal_lab", "int", "Postings from NAICS 5417, 9271 (scientific R&D, space research)"),
        ("n_government", "int", "Postings from NAICS 92xx (all government)"),
        ("n_staffing", "int", "Postings from NAICS 5613 or flagged as staffing"),
        ("n_unclassified", "int", "Postings with NAICS 9999 (unclassified employer)"),
    ]),
    ("D. Labor demand: work mode", [
        ("n_remote", "int", "Postings with remote_type=1 (remote)"),
        ("n_hybrid", "int", "Postings with remote_type=2 (hybrid)"),
        ("n_onsite", "int", "Postings with remote_type=0 (on-site)"),
        ("share_remote", "float [0,1]", "Fraction of postings that are remote"),
        ("share_hybrid", "float [0,1]", "Fraction of postings that are hybrid"),
        ("share_onsite", "float [0,1]", "Fraction of postings that are on-site"),
    ]),
    ("E. Skill demand: composition by skill type", [
        ("share_specialized", "float [0,1]", "Fraction of total skill mentions that are specialized"),
        ("share_software", "float [0,1]", "Fraction of total skill mentions that are software"),
        ("share_common", "float [0,1]", "Fraction of total skill mentions that are common (soft)"),
        ("mean_skills_per_posting", "float", "Average skill mentions per posting in county-year"),
        ("pct_has_skill", "float [0,100]", "Percent of postings with at least one skill"),
    ]),
    ("F. Skill demand: diversity, concentration, and complexity", [
        ("n_distinct_skills", "int", "Count of unique skills demanded in county-year"),
        ("n_rca_skills", "int", "Count of skills with Revealed Comparative Advantage > 1"),
        ("avg_ubiquity", "float", "Mean ubiquity of county's RCA>1 skills (# counties sharing the avg specialization)"),
        ("skill_hhi", "float (0,1]", "Herfindahl-Hirschman concentration over skill frequencies"),
        ("skill_entropy", "float (bits)", "Shannon entropy of skill distribution (effective # skills)"),
        ("eci", "standardized float", "Economic Complexity Index (Hidalgo-Hausmann method of reflections, standardized)"),
        ("fitness", "float (non-negative)", "Tacchella fitness-complexity score (non-linear alternative to ECI)"),
    ]),
    ("G. Skill relatedness and network position", [
        ("skill_density", "float [0,1]", "Balland (2019) avg relatedness of RCA>1 skills to non-RCA skills"),
        ("skill_coherence", "float [0,1]", "Neffke (2011) avg pairwise relatedness among RCA>1 skills"),
        ("avg_centrality", "float [0,1]", "Mean network centrality of county's RCA>1 skills in skill-space network"),
    ]),
    ("H. Skill dynamics: year-over-year", [
        ("churning_entries", "int", "Skills that gained RCA>1 this year vs. prior year"),
        ("churning_exits", "int", "Skills that lost RCA>1 this year vs. prior year"),
        ("churning_net", "int", "churning_entries - churning_exits"),
        ("skill_cosine_distance", "float [0,1]", "1 - cos(skill freq vector t-1, t); structural change in demand profile"),
    ]),
    ("I. Employer-type specialization breadth (consistent measure by entity)", [
        ("corp_n_rca_skills", "int", "Count of skills with corporate-specific RCA>1 (NaN = no corporate postings in cell)"),
        ("univ_n_rca_skills", "int", "Count of skills with university-specific RCA>1 (NaN = no university postings in cell)"),
        ("fede_n_rca_skills", "int", "Count of skills with federal-lab-specific RCA>1 (NaN = no federal-lab postings; ~72% of cells)"),
        ("gove_n_rca_skills", "int", "Count of skills with government-specific RCA>1 (NaN = no government postings in cell)"),
        ("staf_n_rca_skills", "int", "Count of skills with staffing-specific RCA>1 (NaN = no staffing postings in cell)"),
    ]),
]

# Flatten for code that expects a flat list
EXPORT_VARS = []
for group_name, variables in EXPORT_GROUPS:
    for var, vtype, defn in variables:
        EXPORT_VARS.append((var, vtype, defn, group_name))

VAR_NAMES = [v[0] for v in EXPORT_VARS]
VAR_TO_GROUP = {v[0]: v[3] for v in EXPORT_VARS}


def main():
    print("=" * 60)
    print("Building descriptive export")
    print("=" * 60)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs(TABLES_DIR, exist_ok=True)
    os.makedirs(DOC_DIR, exist_ok=True)

    # Load panel
    panel = pd.read_parquet(PANEL_PATH)
    print(f"  Loaded: {panel.shape[0]:,} rows × {panel.shape[1]} cols")

    # Subset
    export = panel[VAR_NAMES].copy()
    print(f"  Export: {export.shape[0]:,} rows × {export.shape[1]} cols")

    # Write parquet and CSV
    parquet_path = f"{EXPORT_DIR}/county_year_panel_export.parquet"
    csv_path = f"{EXPORT_DIR}/county_year_panel_export.csv"
    export.to_parquet(parquet_path, index=False, engine="pyarrow")
    export.to_csv(csv_path, index=False)
    print(f"  Wrote {parquet_path}")
    print(f"  Wrote {csv_path}")

    # Data dictionary
    dd = pd.DataFrame(EXPORT_VARS, columns=["variable", "type", "definition", "category"])
    dd_path = f"{EXPORT_DIR}/data_dictionary.csv"
    dd.to_csv(dd_path, index=False)
    print(f"  Wrote {dd_path}")

    # Summary statistics (5-point + mean + missing)
    numeric_vars = [v for v, t, *_ in EXPORT_VARS if v not in ["county", "year"]]
    stats = export[numeric_vars].describe(percentiles=[0.25, 0.5, 0.75]).T
    stats["missing"] = export[numeric_vars].isna().sum()
    stats["pct_missing"] = (stats["missing"] / len(export) * 100).round(2)
    stats = stats[["count", "missing", "pct_missing", "mean", "std",
                   "min", "25%", "50%", "75%", "max"]]
    stats.columns = ["N", "Missing", "% Missing", "Mean", "SD",
                     "Min", "P25", "P50 (Median)", "P75", "Max"]
    stats_path = f"{EXPORT_DIR}/summary_statistics.csv"
    stats.to_csv(stats_path)
    print(f"  Wrote {stats_path}")

    # Write data dictionary LaTeX fragment
    def esc(s):
        s = str(s)
        s = s.replace("&", "\\&")
        s = s.replace("_", "\\_")
        s = s.replace("%", "\\%")
        s = s.replace("#", "\\#")
        # Wrap math symbols so they render correctly (LaTeX text mode renders
        # > and < oddly under some font setups).
        s = s.replace(">", "$>$").replace("<", "$<$")
        return s

    with open(f"{TABLES_DIR}/tab_data_dictionary.tex", "w") as f:
        f.write("\\begin{longtable}{p{0.30\\textwidth}p{0.18\\textwidth}p{0.46\\textwidth}}\n")
        f.write("\\caption{Data dictionary: variable names, types, and definitions}\n")
        f.write("\\label{tab:data_dictionary} \\\\\n")
        f.write("\\toprule\n")
        f.write("Variable & Type & Definition \\\\\n")
        f.write("\\midrule\n")
        f.write("\\endfirsthead\n")
        f.write("\\multicolumn{3}{c}{\\textit{(continued)}} \\\\\n")
        f.write("\\toprule\n")
        f.write("Variable & Type & Definition \\\\\n")
        f.write("\\midrule\n")
        f.write("\\endhead\n")
        f.write("\\bottomrule\n")
        f.write("\\endlastfoot\n")
        for group_name, variables in EXPORT_GROUPS:
            f.write("\\midrule\n")
            f.write(f"\\multicolumn{{3}}{{l}}{{\\textbf{{{esc(group_name)}}}}} \\\\\n")
            f.write("\\midrule\n")
            for var, vtype, defn in variables:
                f.write(f"\\texttt{{{esc(var)}}} & {esc(vtype)} & {esc(defn)} \\\\\n")
        f.write("\\end{longtable}\n")
    print(f"  Wrote {TABLES_DIR}/tab_data_dictionary.tex")

    # Write summary stats LaTeX fragment (with group headers, longtable)
    with open(f"{TABLES_DIR}/tab_summary_stats.tex", "w") as f:
        f.write("\\begingroup\n\\scriptsize\n")
        f.write("\\setlength{\\tabcolsep}{3pt}\n")
        f.write("\\begin{longtable}{lrrrrrrrrr}\n")
        f.write("\\caption{Summary statistics for county-year panel (2010--2024, N=47{,}891)}\n")
        f.write("\\label{tab:summary_stats} \\\\\n")
        f.write("\\toprule\n")
        f.write("Variable & N & \\%NA & Mean & SD & Min & P25 & Median & P75 & Max \\\\\n")
        f.write("\\midrule\n")
        f.write("\\endfirsthead\n")
        f.write("\\multicolumn{10}{c}{\\textit{(continued)}} \\\\\n")
        f.write("\\toprule\n")
        f.write("Variable & N & \\%NA & Mean & SD & Min & P25 & Median & P75 & Max \\\\\n")
        f.write("\\midrule\n")
        f.write("\\endhead\n")
        f.write("\\bottomrule\n")
        f.write("\\endlastfoot\n")

        # Group headers: span cols 1-4 to keep text within the first part of
        # the row. The remaining 6 numeric columns stay empty in the header row.
        numeric_set = set(stats.index)
        for group_name, variables in EXPORT_GROUPS:
            group_vars_numeric = [v for v, *_ in variables if v in numeric_set]
            if not group_vars_numeric:
                continue
            f.write("\\midrule\n")
            f.write(f"\\multicolumn{{4}}{{l}}{{\\textbf{{{esc(group_name)}}}}} "
                    "& & & & & & \\\\\n")
            f.write("\\midrule\n")
            for var in group_vars_numeric:
                row = stats.loc[var]
                f.write(f"\\texttt{{{esc(var)}}} ")
                f.write(f"& {int(row['N']):,} ")
                f.write(f"& {row['% Missing']:.1f} ")
                for col in ["Mean", "SD", "Min", "P25", "P50 (Median)", "P75", "Max"]:
                    v = row[col]
                    if pd.isna(v):
                        f.write("& --- ")
                    elif abs(v) >= 10000:
                        f.write(f"& {v:,.0f} ")
                    elif abs(v) >= 1:
                        f.write(f"& {v:.2f} ")
                    else:
                        f.write(f"& {v:.3f} ")
                f.write("\\\\\n")
        f.write("\\end{longtable}\n")
        f.write("\\endgroup\n")
    print(f"  Wrote {TABLES_DIR}/tab_summary_stats.tex")

    # Yearly trends table
    yearly = export.groupby("year").agg(
        n_counties=("county", "nunique"),
        total_postings=("total_postings", "sum"),
        median_postings_per_county=("total_postings", "median"),
        median_skill_entropy=("skill_entropy", "median"),
        median_n_rca_skills=("n_rca_skills", "median"),
        median_eci=("eci", "median"),
        median_skill_density=("skill_density", "median"),
        median_churning_net=("churning_net", "median"),
        median_share_remote=("share_remote", "median"),
        median_share_software=("share_software", "median"),
    ).reset_index()
    yearly.to_csv(f"{EXPORT_DIR}/yearly_summary.csv", index=False)
    print(f"  Wrote {EXPORT_DIR}/yearly_summary.csv")

    # ============================================================
    # TIME-SERIES DOT PLOTS (median + IQR by year)
    # ============================================================
    print("\nGenerating time-series plots...")

    ts_vars = [
        ("total_postings", "Total postings per county", True),
        ("skill_entropy", "Skill entropy (bits)", False),
        ("skill_hhi", "Skill concentration (HHI)", False),
        ("n_rca_skills", "Number of RCA>1 skills", False),
        ("eci", "Economic Complexity Index", False),
        ("skill_density", "Skill density (Balland)", False),
        ("skill_coherence", "Skill coherence (Neffke)", False),
        ("share_specialized", "Share specialized skills", False),
        ("share_software", "Share software skills", False),
        ("share_common", "Share common (soft) skills", False),
        ("share_remote", "Share remote postings", False),
        ("share_hybrid", "Share hybrid postings", False),
        ("mean_skills_per_posting", "Mean skills per posting", False),
        ("churning_net", "Net RCA churning (entries - exits)", False),
        ("skill_cosine_distance", "Year-over-year skill vector cosine distance", False),
        ("avg_ubiquity", "Avg ubiquity of county's RCA>1 skills", False),
    ]

    for var, label, log_y in ts_vars:
        fig, ax = plt.subplots(figsize=(7, 4))
        yr_stats = export.groupby("year")[var].agg(
            p25=lambda x: x.quantile(0.25),
            p50="median",
            p75=lambda x: x.quantile(0.75),
        ).reset_index()
        ax.fill_between(yr_stats["year"], yr_stats["p25"], yr_stats["p75"],
                        alpha=0.25, color="steelblue", label="IQR (p25-p75)")
        ax.plot(yr_stats["year"], yr_stats["p50"], "o-", color="steelblue",
                linewidth=2, markersize=6, label="Median")
        ax.set_xlabel("Year")
        ax.set_ylabel(label)
        ax.set_title(f"{label}, county-year panel")
        if log_y:
            ax.set_yscale("log")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9)
        plt.tight_layout()
        fig.savefig(f"{FIGURES_DIR}/ts_{var}.pdf", dpi=200)
        fig.savefig(f"{FIGURES_DIR}/ts_{var}.png", dpi=200)
        plt.close(fig)
    print(f"  Wrote {len(ts_vars)} time-series plots")

    # --- National totals + percent change: shows the structural shocks ---
    yr_totals = export.groupby("year")["total_postings"].sum().reset_index()
    yr_totals["yoy_pct"] = yr_totals["total_postings"].pct_change() * 100

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # LEFT: national total postings (clearly shows 2017-18 jump, 2022 peak)
    ax1.bar(yr_totals["year"], yr_totals["total_postings"] / 1e6,
            color="steelblue", alpha=0.85, edgecolor="black", linewidth=0.5)
    ax1.set_xlabel("Year")
    ax1.set_ylabel("National total postings (millions)")
    ax1.set_title("Total postings (national, summed across counties)")
    # Annotate key years. Offsets staggered to avoid label overlap. Labels kept short.
    annotations = [
        (2018, "+26%\nmethodology", "red",   (-2.5, 12)),
        (2021, "+26%\npost-COVID",  "red",   ( 1.5,  9)),
        (2022, "peak 48.6M",         "black", ( 2.0, 16)),
        (2023, "-20%\ncontraction",  "red",   ( 2.0, 11)),
    ]
    ymax = (yr_totals["total_postings"] / 1e6).max()
    ax1.set_ylim(0, ymax * 1.5)
    for year, label, color, (dx, dy) in annotations:
        val = yr_totals.loc[yr_totals["year"] == year, "total_postings"].iloc[0] / 1e6
        ax1.annotate(label, xy=(year, val), xytext=(year + dx, val + dy),
                     fontsize=7.5, ha="center", va="bottom", color=color,
                     arrowprops=dict(arrowstyle="-", color=color, lw=0.6))
    ax1.grid(True, alpha=0.3, axis="y")

    # RIGHT: YoY percent change (makes jumps/dips visible as bar heights)
    colors = ["darkred" if x < 0 else "steelblue" for x in yr_totals["yoy_pct"].fillna(0)]
    ax2.bar(yr_totals["year"], yr_totals["yoy_pct"], color=colors, alpha=0.85,
            edgecolor="black", linewidth=0.5)
    ax2.axhline(0, color="black", linewidth=0.6)
    ax2.set_xlabel("Year")
    ax2.set_ylabel("Year-over-year change (\\%)")
    ax2.set_title("Year-over-year \\% change in national postings")
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/total_postings_national.pdf", dpi=200)
    fig.savefig(f"{FIGURES_DIR}/total_postings_national.png", dpi=200)
    plt.close(fig)
    print("  Wrote national totals + YoY plot")

    # Composition stack: skill types over time
    fig, ax = plt.subplots(figsize=(7, 4))
    yr_comp = export.groupby("year")[["share_specialized", "share_software", "share_common"]].median().reset_index()
    ax.stackplot(yr_comp["year"],
                 yr_comp["share_specialized"], yr_comp["share_software"], yr_comp["share_common"],
                 labels=["Specialized", "Software", "Common"],
                 colors=["#4C72B0", "#DD8452", "#55A467"], alpha=0.85)
    ax.set_xlabel("Year")
    ax.set_ylabel("Median share of skill mentions")
    ax.set_title("Skill-type composition over time (median county)")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax.set_ylim(0, 1.0)
    plt.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/composition_skill_types.pdf", dpi=200, bbox_inches="tight")
    fig.savefig(f"{FIGURES_DIR}/composition_skill_types.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Work-mode stack
    fig, ax = plt.subplots(figsize=(7, 4))
    yr_wm = export.groupby("year")[["share_onsite", "share_hybrid", "share_remote"]].median().reset_index()
    ax.stackplot(yr_wm["year"],
                 yr_wm["share_onsite"], yr_wm["share_hybrid"], yr_wm["share_remote"],
                 labels=["On-site", "Hybrid", "Remote"],
                 colors=["#937860", "#DA8BC3", "#8172B3"], alpha=0.85)
    ax.set_xlabel("Year")
    ax.set_ylabel("Median share of postings")
    ax.set_title("Work-mode composition over time (median county)")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax.set_ylim(0, 1.0)
    plt.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/composition_work_mode.pdf", dpi=200, bbox_inches="tight")
    fig.savefig(f"{FIGURES_DIR}/composition_work_mode.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Entity-type composition
    fig, ax = plt.subplots(figsize=(7, 4))
    etype_cols = ["n_corporate", "n_university", "n_federal_lab",
                  "n_government", "n_staffing", "n_unclassified"]
    etype_labels = ["Corporate", "University", "Federal Lab",
                    "Government", "Staffing", "Unclassified"]
    yr_et = export.groupby("year")[etype_cols].sum().reset_index()
    yr_et["total"] = yr_et[etype_cols].sum(axis=1)
    for col in etype_cols:
        yr_et[col] = yr_et[col] / yr_et["total"]
    colors = ["#4C72B0", "#DD8452", "#55A467", "#C44E52", "#8172B3", "#937860"]
    ax.stackplot(yr_et["year"],
                 *[yr_et[c] for c in etype_cols],
                 labels=etype_labels, colors=colors, alpha=0.85)
    ax.set_xlabel("Year")
    ax.set_ylabel("Share of total postings")
    ax.set_title("Employer-type composition of postings over time (national aggregate)")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax.set_ylim(0, 1.0)
    plt.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/composition_entity_type.pdf", dpi=200, bbox_inches="tight")
    fig.savefig(f"{FIGURES_DIR}/composition_entity_type.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Entity-specific RCA breadth over time
    fig, ax = plt.subplots(figsize=(7, 4.5))
    breadth_cols = [("corp_n_rca_skills", "Corporate"),
                    ("univ_n_rca_skills", "University"),
                    ("fede_n_rca_skills", "Federal Lab"),
                    ("gove_n_rca_skills", "Government"),
                    ("staf_n_rca_skills", "Staffing")]
    for col, label in breadth_cols:
        yr_med = export.groupby("year")[col].median().reset_index()
        ax.plot(yr_med["year"], yr_med[col], "o-", linewidth=2, markersize=5, label=label)
    ax.set_xlabel("Year")
    ax.set_ylabel("Median # skills with employer-type RCA > 1")
    ax.set_title("Entity-type specialization breadth over time")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/entity_rca_breadth.pdf", dpi=200)
    fig.savefig(f"{FIGURES_DIR}/entity_rca_breadth.png", dpi=200)
    plt.close(fig)

    print("  Wrote composition and entity stacked plots")

    # ============================================================
    # COUNTY MAPS (choropleth, 2024)
    # ============================================================
    print("\nGenerating county maps...")

    # Load FIPS county geojson from plotly
    geojson_url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
    try:
        with urllib.request.urlopen(geojson_url, timeout=30) as resp:
            counties_geo = json.load(resp)
        print("  Loaded US counties geojson")

        map_vars = [
            ("total_postings", "Total postings (log scale)", "Viridis", True),
            ("eci", "Economic Complexity Index", "RdBu_r", False),
            ("skill_entropy", "Skill entropy (bits)", "Viridis", False),
            ("n_rca_skills", "Number of RCA > 1 skills", "Viridis", False),
        ]

        panel_2024 = export[export["year"] == 2024].copy()
        panel_2024["fips"] = panel_2024["county"].astype(str).str.zfill(5)

        for var, label, cmap, log_scale in map_vars:
            data_col = var
            if log_scale:
                panel_2024[f"{var}_log"] = np.log10(panel_2024[var].replace(0, np.nan))
                data_col = f"{var}_log"
                label_use = f"log10({label})"
            else:
                label_use = label

            fig = px.choropleth(
                panel_2024,
                geojson=counties_geo,
                locations="fips",
                color=data_col,
                color_continuous_scale=cmap,
                scope="usa",
                labels={data_col: label_use},
                title=f"{label} by county, 2024",
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=40, b=80),
                font=dict(family="serif", size=12),
                width=900, height=600,
                coloraxis_colorbar=dict(
                    orientation="h",
                    x=0.5, xanchor="center",
                    y=-0.08, yanchor="top",
                    thickness=14,
                    len=0.55,
                    title=dict(text=label_use, side="top"),
                ),
            )
            fig.write_image(f"{FIGURES_DIR}/map_{var}_2024.pdf", scale=2)
            fig.write_image(f"{FIGURES_DIR}/map_{var}_2024.png", scale=2)
        print(f"  Wrote {len(map_vars)} choropleth maps for 2024")

    except Exception as e:
        print(f"  WARNING: map generation failed: {e}")

    # ============================================================
    # LaTeX report
    # ============================================================
    print("\nWriting LaTeX report...")
    write_report()

    print("\nDone. Primary outputs:")
    print(f"  Data: {EXPORT_DIR}/county_year_panel_export.{{parquet,csv}}")
    print(f"  Dictionary: {EXPORT_DIR}/data_dictionary.csv")
    print(f"  Stats: {EXPORT_DIR}/summary_statistics.csv")
    print(f"  Report: {DOC_DIR}/descriptive_report.tex")


def write_report():
    """Emit LaTeX source for the descriptive report."""

    doc = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{array}
\usepackage{caption}
\usepackage{fancyhdr}
\usepackage{xcolor}
\usepackage{cleveref}

\graphicspath{{../../4.results/figures/}}

\title{Lightcast Skills Data Layer\\\large Descriptive Analysis of U.S. County-Level Labor Demand, 2010--2024}
\date{\today}

\begin{document}
\maketitle

\section{Overview}

This document summarizes a county $\times$ year panel built from 433.6 million Lightcast job postings covering 2010--2024 and 3{,}194 U.S. counties. The focus is descriptive: how does the \emph{composition} of labor demand -- volume, skill mix, specialization breadth, concentration, and dynamics -- change over time at the county level? A total of 47{,}891 county-year observations form the analysis sample.

The panel decomposes total postings into six employer types derived from NAICS-4 classifications (\emph{corporate}, \emph{university}, \emph{federal lab}, \emph{government}, \emph{staffing}, \emph{unclassified}). Within each county-year, we measure skill distributional features (Shannon entropy, Herfindahl concentration, share by skill type), revealed comparative advantage (RCA), complexity scores (ECI, fitness-complexity), relatedness-based measures (skill density, coherence, centrality), and year-over-year dynamics (RCA churning, cosine distance on skill frequency vectors).

\textbf{Reading the summary statistics:} all time-series figures in this document plot the \emph{median county} within the IQR band, not a national aggregate. Narrative numbers cited in the text below likewise reference the median-county value unless explicitly labeled \emph{national}.

\section{Outcome Variables for Anchor Entry/Exit Event Studies}
\label{sec:anchor_outcomes}

The panel was constructed to support event-study designs that merge an external dataset of anchor institutions (corporate HQs, universities, federal labs) with entry and exit events. The variables below serve as candidate left-hand-side outcomes and right-hand-side controls when that merge is performed.

\begin{itemize}
\item \textbf{Portfolio-shift outcomes (intensive margin).} \texttt{skill\_cosine\_distance} $\in [0,1]$ measures year-over-year structural change in the county's skill demand profile. It is a direct composite measure of how much anchor entry or exit reshapes local demand, agnostic to which skills shifted.

\item \textbf{Portfolio-shift outcomes (extensive margin).} \texttt{churning\_entries}, \texttt{churning\_exits}, and \texttt{churning\_net} capture skills that newly gain or lose RCA $>$ 1 year-over-year. Anchor entry should show a jump in entries; exit should show a jump in exits.

\item \textbf{Complexity and network-position outcomes.} \texttt{eci} (standardized), \texttt{fitness} (Tacchella), \texttt{skill\_density} (Balland 2019: proximity to acquiring new skills), \texttt{skill\_coherence} (Neffke 2011: internal portfolio integration), and \texttt{avg\_centrality} (position in the skill-space network). These measure whether anchor events move the county up or down the complexity ladder, not just whether the portfolio changed.

\item \textbf{Employer-type-specific outcomes.} For each of corporate, university, federal lab, government, staffing, the panel carries \texttt{\{etype\}\_n\_rca\_skills}, \texttt{\{etype\}\_churning\_entries/exits/net}, and \texttt{\{etype\}\_cosine\_distance}. These decompose the county-level outcome by \emph{which} employer type absorbed the skill-demand shift. For example, when a federal lab enters, one can ask whether corporate skill demand responds (spillover channel) separately from the federal-lab-direct effect.

\item \textbf{Breadth and specialization outcomes.} \texttt{n\_rca\_skills} (total breadth), \texttt{avg\_ubiquity} (how common the county's specializations are nationally), \texttt{skill\_entropy} (effective number of skills), and \texttt{skill\_hhi} (concentration) summarize whether the county's skill portfolio broadened, narrowed, or reorganized.

\item \textbf{Composition controls (RHS).} \texttt{share\_specialized}, \texttt{share\_software}, \texttt{share\_common} (skill-type mix); \texttt{share\_remote}, \texttt{share\_hybrid}, \texttt{share\_onsite} (work mode); \texttt{n\_corporate}, \texttt{n\_university}, \texttt{n\_federal\_lab}, \texttt{n\_government}, \texttt{n\_staffing}, \texttt{n\_unclassified} (employer-type posting counts). These are either exposure measures at baseline or level controls.
\end{itemize}

\textbf{Recommended primary outcomes for event studies.} \texttt{skill\_cosine\_distance} (continuous intensive margin), \texttt{churning\_net} (extensive margin), and the corresponding employer-type-specific versions (\texttt{corp\_cosine\_distance}, \texttt{corp\_churning\_net}) to distinguish direct from spillover effects. Apply a minimum-postings filter (e.g., $\geq$ 50 postings per county-year) for causal work; cosine distance is noisy below that threshold.

\section{Posting Volume and Coverage}

\Cref{fig:national_totals} shows national posting volumes summed across counties, with year-over-year percent changes in the right panel. Three structural features are visible:

\begin{enumerate}
\item \textbf{2017--2018 step-up (+26\%).} Lightcast introduced a methodology change that expanded coverage. This shifts aggregate levels by $\sim$7 million postings per year from 2018 onward.
\item \textbf{No COVID dip.} Posting activity was essentially flat from 2019 to 2020 (+0.7\%). This matches evidence from BLS JOLTS that firms maintained job postings through 2020 even when hiring paused.
\item \textbf{Post-COVID surge then contraction.} Postings jumped +26\% in 2021, peaked at 48.6M in 2022, then contracted $-$20\% in 2023 and $-$5\% in 2024 -- the first sustained decline in the panel.
\end{enumerate}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.95\textwidth]{total_postings_national.pdf}
\caption{National total postings, summed across counties (left), and year-over-year percent change (right). Jumps and contractions are visible in aggregate.}
\label{fig:national_totals}
\end{figure}

\Cref{fig:total_postings} shows the median per-county trajectory. The structural features visible in the national aggregate are \emph{not} as pronounced in the median because posting growth is heavily concentrated in large counties: even the +26\% aggregate jump in 2017--2018 produces only a modest median shift. For cross-year comparisons of county-level outcomes, use shares (composition measures) rather than raw posting levels.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.7\textwidth]{ts_total_postings.pdf}
\caption{Total postings per county over time (median with IQR shading). Structural shocks visible in \Cref{fig:national_totals} are smoothed by the median.}
\label{fig:total_postings}
\end{figure}

\section{Data and Variable Definitions}

The export contains 44 variables, organized into nine groups: (A) unit identifiers, (B--D) labor-demand measures (total postings, postings by employer type, postings by work mode), (E) skill demand composition, (F) skill demand diversity and complexity, (G) skill relatedness and network position, (H) year-over-year skill dynamics, and (I) employer-type specialization breadth as a consistent measure across entity types. Full definitions are in \Cref{tab:data_dictionary}; descriptive summary statistics are in \Cref{tab:summary_stats}.

\textbf{Note on dot plots in this report:} time-series figures plot the median (dot) within the interquartile range (shaded band, $p_{25}$--$p_{75}$). The median is \emph{not} guaranteed to sit at the midpoint of the IQR: for right-skewed distributions (e.g.\ HHI, skill density, ECI) the median sits closer to $p_{25}$; for left-skewed distributions it sits closer to $p_{75}$. A visibly off-center median dot therefore reflects legitimate distributional skewness, not a plotting artifact.

\input{../../4.results/tables/tab_data_dictionary.tex}

\input{../../4.results/tables/tab_summary_stats.tex}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.8\textwidth]{composition_entity_type.pdf}
\caption{Employer-type composition of total postings. Corporate share rises from 46\% (2010) to 65\% (2024) as Lightcast firm identification improves and the \emph{unclassified} share declines from 40\% to 15\%.}
\label{fig:entity_composition}
\end{figure}

\section{Skill Distribution and Composition}

\Cref{fig:entropy} and \Cref{fig:hhi} show how diversified (entropy) and concentrated (HHI) local skill demand is. Entropy rises steadily, consistent with growing skill taxonomy and broader demand; HHI declines in parallel.

\begin{figure}[htbp]
\centering
\begin{minipage}{0.48\textwidth}
\centering
\includegraphics[width=\textwidth]{ts_skill_entropy.pdf}
\caption{Shannon entropy of skill distribution.}
\label{fig:entropy}
\end{minipage}%
\hfill
\begin{minipage}{0.48\textwidth}
\centering
\includegraphics[width=\textwidth]{ts_skill_hhi.pdf}
\caption{Herfindahl concentration (HHI).}
\label{fig:hhi}
\end{minipage}
\end{figure}

\Cref{fig:skill_composition} tracks the composition of skill mentions across specialized, software, and common (soft) skills, at the median county. Specialized skills dominate (stable at $\sim$57\%); common/soft skills are the second-largest group at $\sim$38\% (essentially flat); software is a small but persistent $\sim$3--4\%. The median-county composition is remarkably stable over the full 15-year window. The national aggregate (weighted by total postings) tells a somewhat different story -- software declines from 10\% to 7\% and common rises from 32\% to 37\% -- driven by compositional shifts across counties (e.g., software-heavy Bay Area counties represent a larger or smaller share of total postings in different years), not by a within-county change in employer preferences.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.8\textwidth]{composition_skill_types.pdf}
\caption{Skill-type composition of mentions over time (median county).}
\label{fig:skill_composition}
\end{figure}

\Cref{fig:mean_skills} shows the average number of skill mentions per posting, at the median county. This measure rises from $\sim$6.8 (2010) to $\sim$10.6 (2022--2024). The national aggregate is higher ($\sim$11 rising to $\sim$14), reflecting that higher-volume counties also post more skills per posting on average. Both series indicate broader skill vocabularies and employer tendencies to list more skill requirements per posting over time.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.7\textwidth]{ts_mean_skills_per_posting.pdf}
\caption{Mean skill mentions per posting.}
\label{fig:mean_skills}
\end{figure}

\section{Complexity and Specialization}

\Cref{fig:rca_breadth} reports the median count of skills with county-level RCA $>$ 1. This rises from 500 (2010) to approximately 1{,}200 (2022--2024), tracking both the expanding skill taxonomy and genuine broadening of local specialization.

\Cref{fig:eci,fig:density,fig:coherence} show complexity measures. The Economic Complexity Index (ECI) is standardized, so median values near zero are expected; variation across counties is large (range $\pm$5). Skill density (Balland 2019) rises steadily, indicating counties are moving closer to acquiring new skills. Coherence (Neffke 2011) is stable around 0.22 -- specialization portfolios maintain similar internal relatedness over time, neither tightening nor scattering.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.7\textwidth]{ts_n_rca_skills.pdf}
\caption{Number of skills with RCA $>$ 1 per county (median with IQR).}
\label{fig:rca_breadth}
\end{figure}

\begin{figure}[htbp]
\centering
\begin{minipage}{0.48\textwidth}
\includegraphics[width=\textwidth]{ts_eci.pdf}
\caption{Economic Complexity Index (standardized).}
\label{fig:eci}
\end{minipage}%
\hfill
\begin{minipage}{0.48\textwidth}
\includegraphics[width=\textwidth]{ts_skill_density.pdf}
\caption{Skill density (Balland 2019).}
\label{fig:density}
\end{minipage}
\end{figure}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.7\textwidth]{ts_skill_coherence.pdf}
\caption{Skill coherence (Neffke 2011): average pairwise relatedness among county's RCA $>$ 1 skills.}
\label{fig:coherence}
\end{figure}

\section{Skill Dynamics}

Year-over-year skill portfolio change is captured by RCA churning (extensive margin: new and lost specializations) and cosine distance on frequency vectors (intensive margin: shifts in weights). \Cref{fig:churning_net} shows net churning: counties gained more RCA specializations than they lost throughout the 2010s, with a spike in 2021, then net-negative churning in 2023--2024 reflecting the hiring contraction. \Cref{fig:cosine_dist} shows cosine distance declining over time (0.15 in 2011 $\to$ 0.06 in 2024) -- local demand profiles are becoming more stable, not less.

\begin{figure}[htbp]
\centering
\begin{minipage}{0.48\textwidth}
\centering
\includegraphics[width=\textwidth]{ts_churning_net.pdf}
\caption{Net RCA churning (entries - exits).}
\label{fig:churning_net}
\end{minipage}%
\hfill
\begin{minipage}{0.48\textwidth}
\centering
\includegraphics[width=\textwidth]{ts_skill_cosine_distance.pdf}
\caption{Year-over-year cosine distance of skill freq vectors.}
\label{fig:cosine_dist}
\end{minipage}
\end{figure}

\section{Entity-Type Specialization Breadth}

\Cref{fig:entity_breadth} reports the median count of RCA $>$ 1 skills for each employer type, computed within that type's national skill distribution (min-count 3 filter applied). Corporate portfolios are the broadest; university and federal lab specializations are much narrower, reflecting both smaller posting volumes and more focused skill demand within those employer types.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.8\textwidth]{entity_rca_breadth.pdf}
\caption{Employer-type specialization breadth over time (median county).}
\label{fig:entity_breadth}
\end{figure}

\section{County-Level Heterogeneity (2024)}

Figures~\ref{fig:map_total_postings}--\ref{fig:map_n_rca_skills} present county-level choropleths for four key measures in 2024. \Cref{fig:map_total_postings} shows that total posting volume is concentrated in major metropolitan counties, with most counties producing a far smaller share. \Cref{fig:map_eci} shows the ECI distribution, \Cref{fig:map_skill_entropy} the Shannon entropy of skill demand, and \Cref{fig:map_n_rca_skills} the county count of skills with RCA $>$ 1.

The four maps reveal broadly similar spatial patterns. The same set of counties appears in the upper tail across posting volume, complexity, entropy, and specialization breadth: San Francisco and Santa Clara in the Bay Area; King County (Seattle); Suffolk and Middlesex (Boston corridor); New York and Cook (Chicago); Travis (Austin) and Dallas in Texas; Fairfax, Virginia. Rural counties in the South, Midwest, and Mountain West appear in the lower tail across all four measures. Cross-county variation in skill demand is thus structured along a consistent urban-research gradient, with the same counties ranking high (or low) regardless of which measure is chosen.

\begin{figure}[htbp]
\centering
\includegraphics[width=0.85\textwidth]{map_total_postings_2024.pdf}
\caption{Total postings by county, 2024 (log scale).}
\label{fig:map_total_postings}
\end{figure}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.85\textwidth]{map_eci_2024.pdf}
\caption{Economic Complexity Index by county, 2024.}
\label{fig:map_eci}
\end{figure}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.85\textwidth]{map_skill_entropy_2024.pdf}
\caption{Skill entropy by county, 2024.}
\label{fig:map_skill_entropy}
\end{figure}

\begin{figure}[htbp]
\centering
\includegraphics[width=0.85\textwidth]{map_n_rca_skills_2024.pdf}
\caption{Number of RCA $>$ 1 skills by county, 2024.}
\label{fig:map_n_rca_skills}
\end{figure}

\section{Data Quality Notes}

\begin{itemize}
\item The \emph{unclassified} employer share drops from 40\% (2010) to 15\% (2024), reflecting improved Lightcast firm identification over time. Early-year corporate measures are biased toward larger, identifiable firms.
\item Approximately 95\% of postings list at least one skill, stable over time.
\item Cosine distance is noisy for counties with fewer than 50 postings; analysts should apply a posting threshold for causal work.
\item FIPS codes ending in 999 (state-level unassigned) are over-represented in remote postings. Flag or exclude for county-level analysis.
\item Level comparisons across 2017--2018 are affected by a Lightcast volume methodology change (+26\%). Use shares for cross-year comparison.
\end{itemize}

\end{document}
"""

    with open(f"{DOC_DIR}/descriptive_report.tex", "w") as f:
        f.write(doc)


if __name__ == "__main__":
    main()
