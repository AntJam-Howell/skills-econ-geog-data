# Codebook: County-Year Panel of U.S. Labor and Skill Demand

Human-readable companion to `data_dictionary.csv` (the canonical machine-readable source). The 44 variables in `county_year_panel.parquet` / `county_year_panel.csv` are organized into nine groups (A through I).

| # | Variable | Type | Definition |
|---|---|---|---|
| **A. Unit identifiers** | | | |
| 1 | `county` | string | 5-digit FIPS code |
| 2 | `year` | int | Calendar year, 2010-2024 |
| **B. Labor demand: totals** | | | |
| 3 | `total_postings` | int | Total unique job postings in county-year |
| 4 | `n_has_skill` | int | Postings with at least one skill listed |
| 5 | `mention_specialized` | int | Total mentions of specialized skills |
| 6 | `mention_software` | int | Total mentions of software skills |
| 7 | `mention_common` | int | Total mentions of common (soft) skills |
| 8 | `n_internship` | int | Postings flagged as internships |
| **C. Labor demand: posting counts by employer type** | | | |
| 9 | `n_corporate` | int | Corporate (private-sector) postings with explicit NAICS-4 classification (non-univ/lab/gov/staffing); add `n_unclassified` for the total corporate posting count |
| 10 | `n_university` | int | Postings from NAICS 6112-6117 (universities/colleges) |
| 11 | `n_federal_lab` | int | Postings from NAICS 5417, 9271 (scientific R&D, space research) |
| 12 | `n_government` | int | Postings from NAICS 92xx (all government) |
| 13 | `n_staffing` | int | Postings from NAICS 5613 or flagged as staffing |
| 14 | `n_unclassified` | int | Transparency subset of corporate: postings with NAICS-4 = 9999 |
| **D. Labor demand: work mode** | | | |
| 15 | `n_remote` | int | Postings with `remote_type` = 1 (remote) |
| 16 | `n_hybrid` | int | Postings with `remote_type` = 2 (hybrid) |
| 17 | `n_onsite` | int | Postings with `remote_type` = 0 (on-site) |
| 18 | `share_remote` | float [0,1] | Fraction of postings that are remote |
| 19 | `share_hybrid` | float [0,1] | Fraction of postings that are hybrid |
| 20 | `share_onsite` | float [0,1] | Fraction of postings that are on-site |
| **E. Skill demand: composition by skill type** | | | |
| 21 | `share_specialized` | float [0,1] | Fraction of total skill mentions that are specialized |
| 22 | `share_software` | float [0,1] | Fraction of total skill mentions that are software |
| 23 | `share_common` | float [0,1] | Fraction of total skill mentions that are common (soft) |
| 24 | `mean_skills_per_posting` | float | Average skill mentions per posting in county-year |
| 25 | `pct_has_skill` | float [0,100] | Percent of postings with at least one skill |
| **F. Skill demand: diversity, concentration, and complexity** | | | |
| 26 | `n_distinct_skills` | int | Count of unique skills demanded in county-year |
| 27 | `n_rca_skills` | int | Count of skills with Revealed Comparative Advantage > 1 |
| 28 | `avg_ubiquity` | float | Mean ubiquity of county's RCA > 1 skills (# counties sharing the average specialization) |
| 29 | `skill_hhi` | float (0,1] | Herfindahl-Hirschman concentration over skill frequencies |
| 30 | `skill_entropy` | float (bits) | Shannon entropy of skill distribution (effective number of skills) |
| 31 | `eci` | standardized float | Economic Complexity Index (Hidalgo-Hausmann method of reflections, standardized) |
| 32 | `fitness` | float (non-negative) | Tacchella fitness-complexity score (non-linear alternative to ECI) |
| **G. Skill relatedness and network position** | | | |
| 33 | `skill_density` | float [0,1] | Balland (2019) average relatedness of RCA > 1 skills to non-RCA skills |
| 34 | `skill_coherence` | float [0,1] | Neffke (2011) average pairwise relatedness among RCA > 1 skills |
| 35 | `avg_centrality` | float [0,1] | Mean network centrality of county's RCA > 1 skills in skill-space network |
| **H. Skill dynamics: year-over-year** | | | |
| 36 | `churning_entries` | int | Skills that gained RCA > 1 this year vs. prior year |
| 37 | `churning_exits` | int | Skills that lost RCA > 1 this year vs. prior year |
| 38 | `churning_net` | int | `churning_entries` - `churning_exits` |
| 39 | `skill_cosine_distance` | float [0,1] | 1 - cosine(skill freq vector at t-1, t); structural change in demand profile |
| **I. Employer-type specialization breadth** | | | |
| 40 | `corp_n_rca_skills` | int | Count of skills with corporate-specific RCA > 1 |
| 41 | `univ_n_rca_skills` | int | Count of skills with university-specific RCA > 1 |
| 42 | `fede_n_rca_skills` | int | Count of skills with federal-lab-specific RCA > 1 |
| 43 | `gove_n_rca_skills` | int | Count of skills with government-specific RCA > 1 |
| 44 | `staf_n_rca_skills` | int | Count of skills with staffing-specific RCA > 1 |

## Notes

- **Missing values.** Pre-2018 `share_remote` / `share_hybrid` are NULL by design (Lightcast did not parse the `remote_type` field consistently before 2018).
- **Standardization.** `eci` is standardized to mean 0 and standard deviation 1 within each year.
- **Unit aggregation.** `n_corporate` reports the NAICS-classified corporate slice. `n_unclassified` (NAICS-4 = 9999) is held separately as a transparency diagnostic. Add the two to recover the full corporate posting count for a county-year.
- **Coverage filter.** The panel drops county-years with zero postings. Counties with fewer than ~50 postings produce noisy `skill_cosine_distance` values; apply a posting threshold for causal-inference work.

For background on the construction pipeline, see `code/README.md` and `docs/methodology.md`. For the original variable definitions used by the build scripts, see `data_dictionary.csv`.
