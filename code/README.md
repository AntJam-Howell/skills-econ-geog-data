# Replication scripts

The Python scripts in this directory reproduce the **201-column county-year panel** from the raw Lightcast Main job-posting data. The pipeline is split into one Phase A scan plus two parallel Phase B compute steps. Each script writes its outputs to consistent paths; the released `county_year_panel.parquet` is the result of joining the two Phase B outputs on `(county, year)`.

## Build chain

```
Lightcast Main CSV shards (subscriber-only)
    │
    │  [Script A] build_skill_counts.py        (Phase A: streaming scan)
    ▼
intermediate/scan/year=YYYY/
    ├── skill_counts.parquet                    (county-skill-year totals)
    ├── employer_skill.parquet                  (county-entity-skill-year totals)
    └── panel_stats.parquet                     (county-year posting tallies)
    │
    ├──────────────────────────┐
    │                          │
    │  [Script B]              │  [Script C]
    │  compute_skill_measures  │  compute_phaseb_v2
    │  .py                     │  .py
    ▼                          ▼
core measures (groups A–H)     entity-specific measures
+ entity-pair similarity        (groups I, K)
(group K)
181 columns                    20 columns
    │                          │
    └──────────┬───────────────┘
               │  inner join on (county, year)
               ▼
county_year_panel.parquet      (201-column released panel)
county_year_panel.csv          (CSV mirror)
               │
               │  [Helper] build_descriptive_export.py
               ▼
data_dictionary.csv
summary_statistics.csv
yearly_summary.csv
codebook.md
```

## Which script produces which variables

The 201 released variables are partitioned across the three numbered scripts. Each row of the table below points to the script that emits the column.

| Group | Columns | Description | Produced by |
|---|---|---|---|
| **A** | 2 | Unit identifiers (`county`, `year`) | Script B |
| **B** | 5 | Labor-demand totals + internship count | Script B |
| **C** | 4 | Posting counts by entity type (`n_corporate`, `n_university`, `n_federal_lab`, `n_government`) | Script B |
| **D** | 7 | Modality counts and shares (`n_remote`, `n_hybrid`, `n_onsite`, `share_remote`, `share_hybrid`, `share_onsite`) plus internship count (`n_internship`) | Script B |
| **E** | 5 | Skill composition (totals, distinct skills, type shares) | Script B |
| **F** | 7 | Skill diversity, concentration, complexity (entropy, HHI, ECI, fitness, RCA breadth, ubiquity) | Script B |
| **G** | 3 | Skill-relatedness measures (density, coherence, centrality) | Script B |
| **H** | 4 | Year-over-year dynamics (RCA churning entries / exits / net; cosine distance) | Script B |
| **I** | 4 | Per-entity RCA > 1 breadth (`{entity}_n_rca_skills` × 4) | **Script C** |
| **J** | 16 | Per-entity churning entries / exits / net + within-entity cosine distance, for each of 4 entity types | **Script C** |
| **K** | 144 | Six entity-pair similarity families (cosine, Jaccard, Hidalgo proximity, weighted RCA overlap, gap count, gap relatedness), over six unordered pairs of entity types, each split across {all, specialized, software, common} skill subsets | Script B |
| | **201** | total released variables | |

Groups A–H + K = **181 columns**, written by Script B to `panels/county_year_panel.parquet`.
Groups I + J = **20 columns**, written by Script C and joined onto the panel on `(county, year)`.

Variables and their dtypes are documented in `data/data_dictionary.csv`; variable semantics and construction notes are in `data/codebook.md`.

## Files

- **`build_skill_counts.py`** (Script A — Phase A). Single-pass streaming scan of the raw gzipped CSV shards. Parses pipe-delimited skill mentions, classifies each posting into one of four employer entity types (corporate, university, federal lab, government) from the NAICS-4 field, and aggregates to per-year checkpoint parquets keyed by `(county, skill, entity_type)`. Year-level `_SUCCESS` markers allow restart without re-scanning completed years.
- **`compute_skill_measures.py`** (Script B — Phase B core + Group K). Reads Phase A checkpoints and computes the core measure battery (groups A–H): Balassa revealed comparative advantage at county-skill-year resolution; year-specific skill-skill relatedness matrices (Hidalgo proximity); Balland skill density (averaged over non-RCA skills); Neffke skill coherence; Hidalgo–Hausmann Economic Complexity Index (computed as the second-largest eigenvector of the normalized co-occurrence matrix per Mealy, Farmer & Teytelboym 2019, mathematically equivalent to the converged method of reflections); Tacchella fitness-complexity; year-over-year RCA churning and cosine distance on skill frequency vectors. It additionally computes group K: six families of entity-pair skill-similarity measures (cosine, Jaccard, Hidalgo proximity, weighted RCA overlap, directional gap count, directional gap relatedness) across the six unordered entity-type pairs and four skill-type subsets. Output: `panels/county_year_panel.parquet` (181 columns).
- **`compute_phaseb_v2.py`** (Script C — Phase B entity extension). Reads the same Phase A checkpoints and computes the entity-decomposed extension: per-entity-type Balassa RCA on each entity's own skill pool, then derives group I (RCA > 1 breadth per entity type) and group J (per-entity churning entries / exits / net and within-entity cosine distance). Output: `panels/employer_rca/year=YYYY/employer_rca.parquet`, `panels/employer_dynamics.parquet`, and the 20-column group-I+K extension that is joined onto `county_year_panel.parquet` on `(county, year)` to produce the released 201-column file.
- **`build_descriptive_export.py`** (Documentation helper). Writes the data dictionary, codebook, summary-statistics table, and yearly summary that accompany the released panel.
- **`slurm/`**. SLURM submission scripts documenting the resource configuration used on the ASU Sol HPC cluster. Three scripts mirror the three pipeline stages: `build_skill_counts.slurm` for Phase A (200 GB memory, 16 cores, ~48 h wall time), `compute_measures.slurm` for Script B (200 GB memory, 4 cores, ~1 h wall time), and `compute_phaseb_v2.slurm` for Script C (128 GB memory, 4 cores, ~1–2 h wall time).

## How to run

The three pipeline scripts can be invoked directly with the project's Python interpreter once paths are configured (see "Path configuration" below).

```bash
# Phase A: scan raw Lightcast shards (one-time, ~48 h on Sol)
python build_skill_counts.py

# Phase B core + group K (~1 h on Sol)
python compute_skill_measures.py

# Phase B entity extension: groups I + K (~1–2 h on Sol)
python compute_phaseb_v2.py
```

The two Phase B steps depend only on the Phase A checkpoints; they can run in parallel or in either order. The final 201-column `county_year_panel.parquet` is the inner join of the Script B output and the Script C output on `(county, year)`. The released panel was assembled exactly this way (job `52890793` for Script B and the prior Script C output for the entity extension); re-running both Phase B scripts on the same Phase A checkpoints will reproduce the released panel cell-for-cell.

On an HPC environment with SLURM, the three corresponding `slurm/*.slurm` files can be submitted in sequence:

```bash
sbatch slurm/build_skill_counts.slurm
sbatch --dependency=afterok:<jobid_A> slurm/compute_measures.slurm
sbatch --dependency=afterok:<jobid_A> slurm/compute_phaseb_v2.slurm
```

## Python environment

Developed and tested with **Python 3.11** on the ASU Sol HPC cluster. All package versions are pinned in `requirements.txt`:

```
pip install -r requirements.txt
```

The pinned set covers the three pipeline scripts (pandas, numpy, pyarrow) and the descriptive-export helper (matplotlib, seaborn, plotly). `requirements.txt` is the single source of truth for dependencies; the inline list previously documented here was retired in favour of the machine-readable file.

The pipeline is deterministic given the same input data. We have re-run the full pipeline three times during development and obtained bit-identical output (within parquet write-order noise) each time.

## Hardware

The pipeline was developed on the ASU Sol HPC cluster. Phase A is I/O and memory bound and benefits from 16+ CPU cores and at least 200 GB of memory; Script B is compute bound and benefits from 200 GB of memory for the full-vocabulary skill-skill relatedness matrix; Script C runs in ~128 GB. The scripts can run on a single workstation given sufficient memory, but the wall time will scale roughly linearly with the I/O bandwidth available for reading the raw Lightcast shards.

## Data requirements

The raw Lightcast Main data are available to subscribers under Lightcast's data agreement. Replication from raw data requires a current Lightcast subscription. The released county-year panel can be reproduced using the released code and the subscriber's local Lightcast extract.

## Path configuration

All paths are read from environment variables with sensible relative-path fallbacks; nothing is hardcoded to a particular user or HPC environment.

| Variable | Consumed by | Fallback | Meaning |
|---|---|---|---|
| `LIGHTCAST_RAW_DIR` | `build_skill_counts.py` | `./raw/Main` | Directory holding raw Lightcast Main shards. One subdirectory per year, each containing gzipped CSVs. |
| `LIGHTCAST_DATA_DIR` | `build_skill_counts.py`, `compute_skill_measures.py`, `compute_phaseb_v2.py` | `./processed` | Processed-data root. Phase A writes to `${LIGHTCAST_DATA_DIR}/intermediate/scan`; the two Phase B scripts read those and write to `${LIGHTCAST_DATA_DIR}/panels` and `${LIGHTCAST_DATA_DIR}/rca`. |
| `LIGHTCAST_PANEL_PATH` | `build_descriptive_export.py` | `../data/county_year_panel.parquet` | Path to the released county-year parquet. Default resolves to the panel that ships in this repository. |
| `LIGHTCAST_DESCRIPTIVE_OUTPUT` | `build_descriptive_export.py` | `./descriptive_outputs` | Output base for the documentation regeneration helper (exports, figures, tables, doc). |

Example invocations:

```bash
# Pin everything explicitly:
export LIGHTCAST_RAW_DIR=/path/to/Lightcast/Main
export LIGHTCAST_DATA_DIR=/path/to/processed
python build_skill_counts.py
python compute_skill_measures.py
python compute_phaseb_v2.py

# Or rely on the fallbacks, run from a checkout layout that has
# ./raw/Main and ./processed at the working directory:
python build_skill_counts.py
python compute_skill_measures.py
python compute_phaseb_v2.py
```

The SLURM templates under `slurm/` export the same env vars near the top of each script, with default values that match the ASU Sol layout. Edit those exports (and the `--output` / `--error` / `--mail-user` / `--partition` directives) for any other HPC environment.
