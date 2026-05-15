# U.S. County Panel of Labor and Skill Demand, 2010–2024

A publicly available county-year panel of U.S. labor and skill demand, derived from 433.6 million Lightcast (Burning Glass) job postings spanning 2010–2024. The panel covers 3,194 counties across 15 years (47,891 county-year observations) and reports 201 variables that describe the volume, employer-entity composition, skill content, specialization, complexity, relatedness, dynamics, and sectoral architecture of local labor demand.

The panel is designed to support research on the economic geography of skills: local specializations, relatedness, and complexity; anchor-institution (universities, government, federal research labs) contributions to local skill ecosystems; and tracking local composition and structural change in the skill ecosystem over time.

**Accompanying paper**

> Howell, A., Feldman, M., Lanahan, L., Kalathil, N., & Johnson, E. (2026). *Economic geography of U.S. employer demand: skill specialization, relatedness, and complexity.* Working paper, SSRN. https://ssrn.com/abstract=XXXXXXX

**Accompanying dashboard**

> For interactive exploration without writing code: [https://skills-econ-geog.netlify.app/](https://skills-econ-geog.netlify.app/)

Constructed by Anthony Howell, School of Public Affairs, Arizona State University. Email: Anthony.Howell@asu.edu.

Data files in `data/` are released under CC BY 4.0 (see `LICENSE`). Source code in `code/` is released under MIT (see `LICENSE-CODE`).

---

## Repository layout

```
skills-econ-geog-data/
├── README.md                 # this file
├── CITATION.cff              # citation metadata (GitHub / Zenodo)
├── LICENSE                   # CC BY 4.0 (covers data/)
├── LICENSE-CODE              # MIT (covers code/)
├── data/
│   ├── county_year_panel.parquet    # 18 MB, 201 variables (groups A-K)
│   ├── county_year_panel.csv        # 49 MB CSV mirror
│   ├── data_dictionary.csv          # canonical machine-readable variable metadata (201 rows)
│   ├── codebook.md                  # human-readable variable definitions
│   ├── summary_statistics.csv       # N, mean, SD, min, percentiles, max (200 numeric vars)
│   └── yearly_summary.csv           # national-aggregate values by year
├── code/
│   ├── README.md                    # pipeline diagram and environment
│   ├── build_skill_counts.py        # Phase A: streaming scan of raw shards
│   ├── compute_skill_measures.py    # Phase B: RCA, relatedness, complexity
│   ├── build_descriptive_export.py  # documentation helpers for the public release
│   └── slurm/                       # ASU Sol SLURM submission scripts
└── docs/
    └── methodology.md               # extended methods notes
```

---

## The dataset

The released panel is built from the underlying raw Lightcast (formerly Burning Glass Technologies) job-posting micro data: 929 GB across 22,967 gzipped CSV shards, 433.6 million postings, 2010–2024. The micro data are used under an academic license. The released county-year aggregates in `data/` are derived statistics computed from those postings, not the postings themselves. The construction methodology, variable definitions, and intended analytical uses are described in the accompanying working paper by Howell, Feldman, Lanahan, Kalathil, and Johnson (2026); see Citation below.

### Dimensions

- **Unit of observation:** county-year (5-digit FIPS by calendar year)
- **Years:** 2010–2024 (15 calendar years)
- **Counties:** 3,194 unique FIPS codes
- **Observations:** 47,891 county-years. The panel is unbalanced: counties with zero postings in a given year are dropped.
- **Variables:** 201, organized into eleven groups (A-K). Most descriptive and teaching uses need only the 37 core variables in groups A-H; the remaining 164 variables in groups I, J, and K are intended for sectoral, spillover, and skill-type-specific analyses. The codebook explains how to load only the core subset.

### Variable groups

The 201 variables characterize local labor demand along three conceptual dimensions and split further into a core set (groups A-H) and a sectoral architecture extension (groups I, J, K):

- **Who is hiring** (groups B, C): total posting volume, total skill-mention counts by skill type, and the decomposition of posting counts across four employer entity types (corporate, university, federal lab, government). The corporate category covers all private-sector postings.
- **The nature of work** (group D): modality (remote, hybrid, on-site) and the count of internship-flagged postings.
- **What they demand** (groups E, F, G, H, and the sectoral architecture extensions I, J, K): skill content, composition, diversity, complexity, relatedness, dynamics, entity-type specialization breadth, employer-pair similarity, and per-entity-type dynamics.

The full definition of every variable lives in `data/data_dictionary.csv` and `data/codebook.md`. Most descriptive, teaching, and applied uses need only the 37 core variables in groups A-H; the codebook shows how to load only that subset.

| Group | Subset | Variables | What it captures |
|---|---|---|---|
| **A. Unit identifiers** | core | `county`, `year` | 5-digit FIPS and calendar year |
| **B. Labor demand: totals** | core | 5 variables | Total postings; postings with at least one parsed skill; total mention counts of specialized, software, and common skills |
| **C. Labor demand: entity-type counts** | core | 4 variables | Posting counts in the four entity types: corporate (all private-sector), university, federal lab, government |
| **D. Nature of work: modality and internships** | core | 7 variables | Posting counts and shares for remote, hybrid, and on-site; internship-flagged posting count |
| **E. Skill composition** | core | 5 variables | The three skill-type shares (specialized, software, common); mean skill mentions per posting; the percent of postings with at least one parsed skill |
| **F. Skill diversity, concentration, and complexity** | core | 7 variables | Distinct skill count, RCA > 1 breadth, average ubiquity, Herfindahl-Hirschman concentration, Shannon entropy, Economic Complexity Index, Tacchella fitness-complexity |
| **G. Skill relatedness and network position** | core | 3 variables | Balland skill density, Neffke skill coherence, average network centrality of the county's RCA > 1 skills |
| **H. Year-over-year dynamics** | core | 4 variables | RCA churning entries, exits, net; cosine distance on skill frequency vectors between consecutive years |
| **I. Entity-type specialization breadth** | sectoral architecture extension | 4 variables | RCA > 1 skill count computed within each of the four employer entity types' own skill pools |
| **J. Employer-pair skill similarity** | sectoral architecture extension | 144 variables | Pairwise similarity between the skill-frequency vectors of six entity-type pairs (univ-corp, fede-corp, gove-corp, univ-fede, univ-gove, fede-gove), in six measure families (cosine, Jaccard, Hidalgo proximity, weighted RCA overlap, directional gap count, directional gap relatedness), each over all skills and separately over specialized / software / common splits |
| **K. Per-employer-type skill dynamics** | sectoral architecture extension | 16 variables | Year-over-year churning entries, exits, net, and cosine distance computed separately within each of the four entity types' own skill pools |

### What the sectoral architecture extension (groups I, J, K) enables

The 164 variables in groups I-K are designed for four research questions that the aggregate core measures cannot answer:

1. **Sector-by-sector specialization patterns.** Group I reports each entity type's own RCA > 1 skill count: how broadly each sector specializes, and which sectors lead the local skill ecosystem.
2. **Sectoral skill alignment.** Group J operationalizes "how aligned is the university's, federal lab's, or government's skill demand with the local corporate sector's?" The core entity posting counts say how many jobs each sector posted; `cosine_univ_corp` says whether those jobs overlap with what local corporate already specializes in.
3. **Directional skill gaps.** `gap_count_univ_corp` and `gap_relatedness_univ_corp` answer "which university specializations does local corporate lack, and how close are they to skills it has?" The same logic extends to fede-corp and univ-fede pairs.
4. **Differential dynamics by entity type.** Group K lets researchers decompose how each sector's skill portfolio evolves: do corporate, university, federal-lab, and government skill demands change together, or do their trajectories diverge?

Each measure in group J is reported in four versions: pooled across all skills, and separately over specialized, software, and common skill subsets. This allows skill-type-specific claims (for example, "the university brings new specialized skills but duplicates existing common skills").

### Employer entity types

Each posting is assigned to exactly one of four entity types. Assignment uses the posting's NAICS-4 code:

| Type | NAICS-4 codes |
|---|---|
| University | 6112, 6113, 6114, 6115, 6116, 6117 |
| Federal lab | 5417, 9271 |
| Government | 92xx (all) |
| Corporate | all remaining postings (the full private sector) |

In the data file, `n_corporate` reports all private-sector postings in the county-year, regardless of NAICS-4 specificity.

---

## Interactive dashboard

A companion web dashboard visualizes the released county-year panel. It is intended for readers, students, and policy users who want to explore the data without writing code.

- **Hosted version:** [https://skills-econ-geog.netlify.app/](https://skills-econ-geog.netlify.app/) (open access, no credentials required).

The dashboard has five pages:

| Page | What it shows |
|---|---|
| **Spatial visualization** | County-level choropleth map of any panel variable, with a year slider and play button to animate 2010–2024. The default landing metric is local specializations (`n_rca_skills`). |
| **Rankings & trends** | Top-25 ranked table for the selected metric and year, distribution histogram, and four national-context charts that put the core measures in 2010–2024 perspective. |
| **County comparisons** | Bivariate scatter of any two panel variables for a selected year, with a focal county and its k-nearest peers highlighted. |
| **County profiles** | In-depth single-county trajectory across the full 15-year window, with sparklines for the core measures and stacked composition plots for the work-mode and skill-type shares. |
| **How to use the dashboard** | Layered usage guide: data source, metric glossary, four numbered workflows, and a methodology summary. |

---

## Quick start

### Python

```python
import pandas as pd
panel = pd.read_parquet("data/county_year_panel.parquet")

# or with polars:
import polars as pl
panel = pl.read_parquet("data/county_year_panel.parquet")
```

To load only the 37 core variables (groups A-H), see the column list in `data/codebook.md` and pass it via the `columns=` argument to `read_parquet`.

### R

```r
library(arrow)
panel <- read_parquet("data/county_year_panel.parquet")
```

### DuckDB (SQL over parquet)

```sql
SELECT county, year, eci, skill_density, churning_net
FROM 'data/county_year_panel.parquet'
WHERE year = 2023 AND total_postings >= 1000
ORDER BY eci DESC
LIMIT 25;
```

---

## Reproducing from raw data

The `code/` subdirectory contains the Python pipeline that produced the panel from the raw Lightcast Main job-posting data.

1. **`code/build_skill_counts.py`** (Phase A). Streams through the raw gzipped CSV shards, parses pipe-delimited skill mentions, classifies each posting into an entity type, and aggregates to per-year checkpoint parquets keyed by county and skill.
2. **`code/compute_skill_measures.py`** (Phase B). Reads the Phase A checkpoints and computes the full battery of derived measures: revealed comparative advantage, skill-skill relatedness, skill density, coherence, ECI, fitness-complexity, year-over-year dynamics, entity-type specialization measures, employer-pair similarity (group J), and per-entity dynamics (group K). The Phase B output is published as `data/county_year_panel.parquet` (129 columns).
3. **`code/build_descriptive_export.py`** (Export helpers). Writes the data dictionary, codebook, and summary-statistics table that accompany the panel.

SLURM job scripts that document the resource configuration used on the ASU Sol HPC cluster are in `code/slurm/`. Extended methods notes are in `docs/methodology.md`.

The raw Lightcast Main data are available to subscribers under Lightcast's data agreement. Replication from raw data requires a current Lightcast subscription.

### Python environment

The pipeline was developed and tested with Python 3.11 and the following key packages: `pandas`, `numpy`, `pyarrow`, `polars`, `scipy`, `scikit-learn`. The pipeline is deterministic given the same input data.

---

## Citation

If you use this dataset, please cite:

> Howell, A. (2026). *U.S. County-Year Panel of Labor and Skill Demand, 2010–2024* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.XXXXXXX

For the accompanying working paper, see the top of this README.

---

## License

- **Data files** (`data/*.parquet`, `data/*.csv`): released under Creative Commons Attribution 4.0 International (CC BY 4.0). Full license text in `LICENSE`. The derived measures are aggregated statistics computed from the underlying Lightcast micro data; the Lightcast license governs the raw data, not these aggregates.
- **Source code** (`code/*.py`, `code/slurm/*.slurm`): released under the MIT License. Full license text in `LICENSE-CODE`.

---

## Acknowledgments

This material is based upon work supported by the National Science Foundation under Grant No. 2431853. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author and do not necessarily reflect the views of the National Science Foundation.
