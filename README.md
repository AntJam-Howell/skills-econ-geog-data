# U.S. County-Year Panel of Labor and Skill Demand, 2010–2024

A publicly available county-year panel of U.S. labor and skill demand, derived from 433.6 million Lightcast (Burning Glass) job postings spanning 2010–2024. The panel covers 3,194 counties across 15 years (47,891 county-year observations) and reports 44 variables that describe the volume, employer-entity composition, skill content, specialization, complexity, relatedness, and dynamics of local labor demand.

The panel is designed to support research on the economic geography of skills: local specializations, relatedness, and complexity; anchor-institution (universities, government, federal research labs) contributions to local skill ecosystems; and tracking local composition and structural change in the skill ecosystem over time.

**Accompanying paper**

> Howell, A., Feldman, M., Lanahan, L., Kalathil, N., & Johnson, E. (2026). *Economic geography of U.S. employer demand: skill specialization, relatedness, and complexity.* Working paper, SSRN. https://ssrn.com/abstract=XXXXXXX

**Accompanying dashboard**

> For interactive exploration without writing code: [https://antjam-howell.github.io/skills-econ-geog-dashboard/](https://antjam-howell.github.io/skills-econ-geog-dashboard/)

Constructed by Anthony Howell, School of Public Affairs, Arizona State University.

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
│   ├── county_year_panel.parquet    # 9.1 MB primary release
│   ├── county_year_panel.csv        # 20 MB CSV mirror
│   ├── data_dictionary.csv          # canonical machine-readable variable metadata
│   ├── codebook.md                  # human-readable variable definitions
│   ├── summary_statistics.csv       # N, mean, SD, min, percentiles, max
│   └── yearly_summary.csv           # national-aggregate values by year
├── code/
│   ├── README.md                    # pipeline diagram and environment
│   ├── build_skill_counts.py        # Phase A: streaming scan of raw shards
│   ├── compute_skill_measures.py    # Phase B: RCA, relatedness, complexity
│   ├── build_descriptive_export.py  # 44-variable public-release export
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
- **Variables:** 44

### Variable groups

The 44 variables characterize local labor demand along three dimensions:

- **Who is hiring** (groups B, C): total posting volume and the decomposition across the five employer entity types (corporate, university, federal or public lab, government, third-party staffing). The corporate category covers private-sector postings, including those whose detailed NAICS classification is missing (tracked separately by the transparency column `n_unclassified`).
- **The nature of work** (group D, plus internship counts in group B): modality (remote, hybrid, on-site) and internship status.
- **What they demand** (groups E, F, G, H, I): skill content, composition, diversity, complexity, relatedness, dynamics, and entity-type specialization breadth.

Entity-type decomposition in the released panel is limited to posting counts (group C) and the RCA-breadth count (group I). The complexity, relatedness, and dynamics measures (groups F, G, H) are aggregate county-year measures pooled across all entity types. See `data/data_dictionary.csv` or `data/codebook.md` for the exact definition of each variable.

| Group | Variables | What it captures |
|---|---|---|
| **A. Unit identifiers** | `county`, `year` | 5-digit FIPS and calendar year |
| **B. Labor demand: totals** | 6 variables | Total postings, postings with skills, skill-mention totals by skill type, internship counts |
| **C. Labor demand: entity-type counts** | 6 variables | Posting counts in the five entity types (corporate, university, federal lab, government, staffing) plus a transparency column `n_unclassified` for the subset of corporate postings with NAICS-4 = 9999 |
| **D. Labor demand: work mode** | 6 variables | Counts and shares of remote, hybrid, and on-site postings |
| **E. Skill composition** | 5 variables | Shares of specialized, software, and common-soft skill mentions; mean skills per posting; coverage |
| **F. Skill diversity, concentration, and complexity** | 7 variables | Distinct skill count, RCA > 1 breadth, average ubiquity, Herfindahl-Hirschman concentration, Shannon entropy, Economic Complexity Index, Tacchella fitness-complexity |
| **G. Skill relatedness and network position** | 3 variables | Balland skill density, Neffke skill coherence, average network centrality of the county's RCA > 1 skills |
| **H. Year-over-year dynamics** | 4 variables | RCA churning entries, exits, net; cosine distance on skill frequency vectors between consecutive years |
| **I. Entity-type specialization breadth** | 5 variables | RCA > 1 skill count computed within each employer entity type |

### Employer entity types

Each posting is assigned to exactly one of five entity types. Assignment uses the posting's NAICS-4 code and the Lightcast staffing flag:

| Type | NAICS-4 codes |
|---|---|
| University | 6112, 6113, 6114, 6115, 6116, 6117 |
| Federal/public lab | 5417, 9271 |
| Government | 92xx (all) |
| Staffing | NAICS 5613 or Lightcast `company_is_staffing == True` |
| Corporate | all remaining postings (private-sector, including those with NAICS-4 = 9999) |

In the data file, `n_corporate` and `n_unclassified` are separate columns. `n_corporate` reports NAICS-classified private-sector postings; `n_unclassified` reports postings with NAICS-4 = 9999. To recover the total private-sector posting count for a county-year, sum the two columns.

---

## Interactive dashboard

A companion web dashboard visualizes the released county-year panel. It is intended for readers, students, and policy users who want to explore the data without writing code.

- **Hosted version:** [https://antjam-howell.github.io/skills-econ-geog-dashboard/](https://antjam-howell.github.io/skills-econ-geog-dashboard/) (open access, no credentials required).

The dashboard has five pages:

| Page | What it shows |
|---|---|
| **Spatial visualization** | County-level choropleth map of any panel variable, with a year slider and play button to animate 2010–2024. The default landing metric is local specializations (`n_rca_skills`). |
| **Rankings & trends** | Top-25 ranked table for the selected metric and year, distribution histogram, and four national-context charts that put the headline measures in 2010–2024 perspective. |
| **County comparisons** | Bivariate scatter of any two panel variables for a selected year, with a focal county and its k-nearest peers highlighted. |
| **County profiles** | In-depth single-county trajectory across the full 15-year window, with sparklines for the headline measures and stacked composition plots for the work-mode and skill-type shares. |
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
2. **`code/compute_skill_measures.py`** (Phase B). Reads the Phase A checkpoints and computes the full battery of derived measures: revealed comparative advantage, skill-skill relatedness, skill density, coherence, ECI, fitness-complexity, year-over-year dynamics, and the entity-type specialization measures retained in the released panel.
3. **`code/build_descriptive_export.py`** (Export). Subsets the full-pipeline output to the 44-variable public release, writes `county_year_panel.parquet` and `county_year_panel.csv`, the data dictionary, and the summary-statistics table.

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

## Contact and research collaborations

This release contains the headline county-year panel. The construction pipeline also produces several research-team artifacts that either underpin the released measures (the county-skill-year long table of mention counts, the entity-type-specific RCA tables, and the year-specific skill-skill relatedness matrices) or extend them (384-dimensional semantic embeddings of the 29,256 skill names; finer-grained entity-pair similarity statistics; per-entity year-over-year dynamics statistics). None of these are part of the public release.

Researchers interested in applications that operate at the underlying skill level are encouraged to contact the author for collaborative research. Examples include projecting published AI-exposure scores onto local skill demand via the semantic embeddings, decomposing the complexity and relatedness measures by entity type, building alternative RCA thresholds, and studying knowledge spillovers via entity-pair similarity.

**Anthony Howell**
Associate Professor, School of Public Affairs
Director, Center on Technology, Data & Society
Arizona State University
Email: ajhowel5@asu.edu

---

## Acknowledgments

This material is based upon work supported by the National Science Foundation under Grant No. 2431853. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author and do not necessarily reflect the views of the National Science Foundation.
