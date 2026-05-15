# Replication scripts

The Python scripts in this directory reproduce the county-year panel from the raw Lightcast Main job-posting data.

## Pipeline

```
Lightcast Main CSV shards (subscriber-only)
    │
    │  build_skill_counts.py        (Phase A: streaming scan)
    ▼
intermediate/scan/year=YYYY/        (per-year checkpoint parquets)
    │
    │  compute_skill_measures.py    (Phase B: RCA, relatedness, density,
    │                                 coherence, ECI, fitness, dynamics,
    │                                 employer-pair similarity, per-entity
    │                                 dynamics)
    ▼
county_year_panel.parquet           (129-column Phase B output, published directly)
county_year_panel.csv               (CSV mirror of the same panel)
    │
    │  build_descriptive_export.py  (documentation helpers)
    ▼
data_dictionary.csv
summary_statistics.csv
yearly_summary.csv
codebook.md
```

## Files

- **`build_skill_counts.py`** (Phase A). Single-pass streaming scan of the raw gzipped CSV shards. Parses pipe-delimited skill mentions, classifies each posting into one of four employer entity types (corporate, university, federal lab, government) from the NAICS-4 field, and aggregates to per-year checkpoint parquets keyed by (county, skill, entity\_type). Year-level `_SUCCESS` markers allow restart without re-scanning completed years.
- **`compute_skill_measures.py`** (Phase B). Reads Phase A checkpoints and computes the full battery of derived measures: Balassa revealed comparative advantage at county-skill-year resolution; year-specific skill-skill relatedness matrices (Hidalgo proximity); Balland skill density; Neffke skill coherence; Hidalgo-Hausmann Economic Complexity Index (method of reflections, 20 iterations); Tacchella fitness-complexity (50 iterations); year-over-year RCA churning and cosine distance on skill frequency vectors; entity-type specialization breadth.
- **`build_descriptive_export.py`** (Documentation helpers). Writes the data dictionary, codebook, summary-statistics table, and yearly summary that accompany the 129-column Phase B output. The panel itself (`county_year_panel.parquet` / `.csv`) is the direct Phase B output and requires no additional script.
- **`slurm/`**. SLURM submission scripts that document the resource configuration used on the ASU Sol HPC cluster (200 GB memory, 16 cores; Phase A wall time approximately 48 hours; Phase B approximately 1 hour).

## Python environment

Developed and tested with Python 3.11. Key package versions:

```
pandas       == 3.0.2
numpy        == 2.4.4
pyarrow      == 22.0.0
polars       == 1.36.0
scipy        == 1.16.4
scikit-learn == 1.7.4
```

The pipeline is deterministic given the same input data. We have re-run the full pipeline three times during development and obtained bit-identical output (within parquet write-order noise) each time.

## Hardware

The pipeline was developed on the ASU Sol HPC cluster. Phase A is I/O and memory bound and benefits from 16+ CPU cores and at least 200 GB of memory; Phase B is compute bound and fits within 64 GB of memory. The scripts can run on a single workstation given sufficient memory, but the wall time will scale roughly linearly with the I/O bandwidth available for reading the raw Lightcast shards.

## Data requirements

The raw Lightcast Main data are available to subscribers under Lightcast's data agreement. Replication from raw data requires a current Lightcast subscription. The released county-year panel can be reproduced using the released code and the subscriber's local Lightcast extract.

## Path configuration

The scripts read paths from constants near the top of each file (e.g. `DATA_BASE`, `OUTPUT_DIR`). These point to the ASU Sol cluster paths used during development. Adjust them to your local environment before running.
