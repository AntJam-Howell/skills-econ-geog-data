# Codebook: County-Year Panel of U.S. Labor and Skill Demand

Human-readable companion to `data_dictionary.csv` (the canonical machine-readable source). One file (`county_year_panel.parquet` / `county_year_panel.csv`) reports 201 variables for 47,891 county-year observations covering 3,194 counties from 2010 to 2024.

## Recommended starting subset (37 core variables)

Most descriptive, teaching, and applied uses only need the 37 variables in groups A through H. These are the core measures of labor and skill demand and are sufficient for analyses that treat the county-year as the analytic unit without decomposing the entity-type aspect of skill demand. The remaining 164 variables (groups I, J, and K) are intended for sectoral, spillover, and skill-type-specific analyses; see "When you need the full 201" below.

To load only the 37 core variables in Python:

```python
import pandas as pd
CORE = [
    "county", "year",
    # B
    "total_postings", "n_has_skill", "mention_specialized", "mention_software",
    "mention_common",
    # C
    "n_corporate", "n_university", "n_federal_lab", "n_government",
    # D
    "n_remote", "n_hybrid", "n_onsite", "share_remote", "share_hybrid",
    "share_onsite", "n_internship",
    # E
    "share_specialized", "share_software", "share_common",
    "mean_skills_per_posting", "pct_has_skill",
    # F
    "n_distinct_skills", "n_rca_skills", "avg_ubiquity", "skill_hhi",
    "skill_entropy", "eci", "fitness",
    # G
    "skill_density", "skill_coherence", "avg_centrality",
    # H
    "churning_entries", "churning_exits", "churning_net", "skill_cosine_distance",
]
panel = pd.read_parquet("data/county_year_panel.parquet", columns=CORE)
```

## Variable groups

The 201 variables are organized into eleven groups (A through K). Groups A-H are the core subset; groups I, J, and K are the entity-decomposed extension.

| # | Variable | Type | Definition |
|---|---|---|---|
| **A. Unit identifiers** *(core)* | | | |
| 1 | `county` | string | 5-digit FIPS code (zero-padded for single-digit state codes) |
| 2 | `year` | int | Calendar year, 2010-2024 |
| **B. Labor demand: posting and skill-mention totals** *(core)* | | | |
| 3 | `total_postings` | int | Total unique job postings in county-year |
| 4 | `n_has_skill` | int | Postings with at least one skill listed |
| 5 | `mention_specialized` | int | Total mentions of specialized skills |
| 6 | `mention_software` | int | Total mentions of software skills |
| 7 | `mention_common` | int | Total mentions of common skills |
| **C. Labor demand: posting counts by employer type** *(core)* | | | |
| 8 | `n_corporate` | int | All private-sector postings in the county-year (any NAICS classification other than university, federal lab, or government) |
| 9 | `n_university` | int | Postings from NAICS 6112-6117 (universities/colleges) |
| 10 | `n_federal_lab` | int | Postings from NAICS 5417, 9271 (scientific R&D, space research) |
| 11 | `n_government` | int | Postings from NAICS 92xx (all government) |
| **D. Nature of work: modality and internships** *(core)* | | | |
| 12 | `n_remote` | int | Postings with `remote_type` = 1 (remote) |
| 13 | `n_hybrid` | int | Postings with `remote_type` = 2 (hybrid) |
| 14 | `n_onsite` | int | Postings with `remote_type` = 0 (on-site) |
| 15 | `share_remote` | float [0,1] | Fraction of postings that are remote |
| 16 | `share_hybrid` | float [0,1] | Fraction of postings that are hybrid |
| 17 | `share_onsite` | float [0,1] | Fraction of postings that are on-site |
| 18 | `n_internship` | int | Postings flagged as internships |
| **E. Skill demand: composition by skill type** *(core)* | | | |
| 19 | `share_specialized` | float [0,1] | Fraction of total skill mentions that are specialized |
| 20 | `share_software` | float [0,1] | Fraction of total skill mentions that are software |
| 21 | `share_common` | float [0,1] | Fraction of total skill mentions that are common |
| 22 | `mean_skills_per_posting` | float | Average skill mentions per posting in county-year |
| 23 | `pct_has_skill` | float [0,100] | Percent of postings with at least one skill |
| **F. Skill demand: diversity, concentration, and complexity** *(core)* | | | |
| 24 | `n_distinct_skills` | int | Count of unique skills demanded in county-year |
| 25 | `n_rca_skills` | int | Count of skills with Revealed Comparative Advantage > 1 |
| 26 | `avg_ubiquity` | float | Mean ubiquity of county's RCA > 1 skills (# counties sharing the average specialization) |
| 27 | `skill_hhi` | float (0,1] | Herfindahl-Hirschman concentration over skill frequencies |
| 28 | `skill_entropy` | float (bits) | Shannon entropy of skill distribution (effective number of skills) |
| 29 | `eci` | standardized float | Economic Complexity Index (Hidalgo-Hausmann method of reflections, standardized) |
| 30 | `fitness` | float (non-negative) | Tacchella fitness-complexity score (non-linear alternative to ECI) |
| **G. Skill relatedness and network position** *(core)* | | | |
| 31 | `skill_density` | float [0,1] | Balland (2019) skill density: per-county average, taken over the county's non-RCA skills, of each non-RCA skill's average relatedness to the county's RCA > 1 portfolio. Predicts which skills the county is likely to acquire next. |
| 32 | `skill_coherence` | float [0,1] | Neffke (2011) average pairwise relatedness among RCA > 1 skills |
| 33 | `avg_centrality` | float [0,1] | Mean network centrality of county's RCA > 1 skills in skill-space network |
| **H. Skill dynamics: year-over-year** *(core)* | | | |
| 34 | `churning_entries` | int | Skills that gained RCA > 1 this year vs. prior year |
| 35 | `churning_exits` | int | Skills that lost RCA > 1 this year vs. prior year |
| 36 | `churning_net` | int | `churning_entries` - `churning_exits` |
| 37 | `skill_cosine_distance` | float [0,1] | 1 - cosine(skill freq vector at t-1, t); structural change in demand profile |
| **I. Employer-type specialization breadth** *(entity-decomposed extension)* | | | |
| 38 | `corp_n_rca_skills` | int | Count of skills with corporate-specific RCA > 1 |
| 39 | `univ_n_rca_skills` | int | Count of skills with university-specific RCA > 1 |
| 40 | `fede_n_rca_skills` | int | Count of skills with federal-lab-specific RCA > 1 |
| 41 | `gove_n_rca_skills` | int | Count of skills with government-specific RCA > 1 |

---

## When you need the full 201 (groups I, J, K)

Four classes of research questions require variables beyond the 37 core measures. If your analysis falls into one of these, use the corresponding group.

1. **Sector-by-sector specialization patterns.** How broadly does each entity type specialize, and which entity types lead the local skill ecosystem? Group I.
2. **Sectoral skill alignment.** How aligned is the university's, federal lab's, or government's skill demand with the local corporate sector's, and how does that alignment vary across counties, time, and skill types? Group J.
3. **Directional skill gaps.** Which specializations does one sector have that another sector lacks, and how close are the gap skills, in skill space, to the second sector's current strengths? Group J (`gap_count_*`, `gap_relatedness_*`).
4. **Differential dynamics by entity type.** Do corporate, university, federal-lab, and government skill demands evolve together over time, or do their trajectories diverge? Group K.

### Group I. Entity-type specialization breadth (4 variables)

For each of the four entity types (corporate, university, federal lab, government), the count of skills with entity-specific RCA > 1. The entity-specific RCA computes the Balassa formula on each entity type's own skill pool. See variables 38--41 in the table above.

### Group J. Employer-pair skill similarity (144 variables)

Pairwise comparisons between the skill-frequency vectors of three employer-type pairs: `univ_corp` (university vs corporate), `fede_corp` (federal lab vs corporate), and `univ_fede` (university vs federal lab). Six measure families (cosine, Jaccard, Hidalgo proximity, weighted RCA overlap, directional gap count, directional gap relatedness) are each computed in four versions: over all skills, over specialized skills only, over software skills only, and over common skills only. Total: 6 pairs × 6 families × 4 skill-type splits = 144 variables.

| Family | Pattern | Type | What it captures |
|---|---|---|---|
| Cosine similarity | `cosine_{a}_{b}[_{st}]` | float [0,1] | Alignment of the two entity types' skill-frequency vectors. Higher means more similar demand profiles. |
| Jaccard | `jaccard_{a}_{b}[_{st}]` | float [0,1] | Overlap in RCA > 1 skill sets: \|intersection\| / \|union\|. Higher means greater overlap in what each entity type specializes in. |
| Hidalgo proximity | `hidalgo_{a}_{b}[_{st}]` | float [0,1] | Average pairwise skill-skill relatedness between the two RCA > 1 portfolios using the national skill-space network. Captures nearby skills, not only exact overlap. |
| Weighted RCA overlap | `rca_overlap_{a}_{b}[_{st}]` | float | Among the {a}-RCA > 1 skill set, the average {b}-sector RCA. High values mean the {a} sector demands skills the {b} sector already specializes in. |
| Gap count (directional) | `gap_count_{a}_{b}[_{st}]` | int | Number of {a}-RCA > 1 skills for which the {b} sector does NOT have RCA > 1. Inventory of {a}-only specializations. |
| Gap relatedness (directional) | `gap_relatedness_{a}_{b}[_{st}]` | float [0,1] | Average relatedness between the gap skills (from `gap_count`) and the {b}-sector's RCA > 1 portfolio. How close the {a}-only skills are to {b}'s current strengths. |

Naming convention: `{pair}` is one of `univ_corp`, `fede_corp`, `univ_fede`. `{st}` is omitted (all skills) or one of `specialized`, `software`, `common`. Example: `hidalgo_univ_corp_specialized` is the Hidalgo proximity between the university and corporate skill portfolios computed on specialized skills only.

### Group K. Per-employer-type skill dynamics (16 variables)

Year-over-year change in each entity type's own skill demand. The aggregate dynamics in group H pool postings across entity types; group K decomposes those dynamics so that sector-specific shifts can be separated from aggregate shifts. Four entity types × four dynamics measures = 16 variables.

| Pattern | Type | What it captures |
|---|---|---|
| `{e}_churning_entries` | int | Skills that crossed into RCA > 1 in the {e}-sector skill pool this year vs. prior year. |
| `{e}_churning_exits` | int | Skills that fell below RCA > 1 in the {e}-sector skill pool this year vs. prior year. |
| `{e}_churning_net` | int | Net change in the {e}-sector RCA > 1 breadth between consecutive years (entries minus exits). |
| `{e}_cosine_distance` | float [0,1] | 1 - cosine(skill-frequency vector of {e}-sector postings at t-1, t); structural change in the {e}-sector skill-demand profile between consecutive years. |

`{e}` is one of `corp`, `univ`, `fede`, `gove`. Caveat: in county-years with low entity-type posting counts (e.g., `fede_*` outside the few county-years with active federal-lab postings), these measures are noisy. Apply a per-entity posting threshold for causal-inference work.

---

## Notes

- **Standardization.** `eci` is standardized to mean 0 and standard deviation 1 within each year.
- **Coverage filter.** The panel drops county-years with zero postings. Counties with fewer than ~50 postings produce noisy `skill_cosine_distance` values; apply a posting threshold for causal-inference work.
- **Work-mode reconciliation.** `n_remote + n_hybrid + n_onsite` sums to a count slightly less than `total_postings`. The gap reflects postings whose modality could not be assigned to one of the three categories; treat `total_postings - (n_remote + n_hybrid + n_onsite)` as "modality not classified." The gap is small overall and somewhat larger in early years.
- **Entity-decomposed extension small-N caveats.** Groups I, J, and K all depend on the underlying entity-type's posting count in the county-year. They are most reliable for `corp` and `univ`, less reliable for `fede` (only a small subset of county-years contain federal-lab postings) and `gove`. The same `total_postings >= 50` filter that applies to the core dynamics applies to group K; the recommended additional rule for group J is an entity-specific minimum (e.g., both entities in the pair having at least 50 own-postings) before treating a similarity value as informative.
- **Skill-type splits in group J.** The `_specialized` / `_software` / `_common` variants are computed by restricting the underlying skill-frequency vectors and the RCA binarization to mentions of the named skill type only. The unsuffixed variants (e.g., `cosine_univ_corp`) pool across all three skill types.

For background on the construction pipeline, see `code/README.md` and `docs/methodology.md`. For the original variable definitions used by the build scripts, see `data_dictionary.csv`.
