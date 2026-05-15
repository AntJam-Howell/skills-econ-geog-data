# Methodology

Extended methodology notes for the county-year panel of U.S. labor and skill demand, 2010-2024. For the canonical methods description, see the accompanying *Scientific Data* article (under review). For variable definitions, see `data/codebook.md`. For the pipeline implementation, see `code/`.

## 1. Source data

The panel is derived from the Lightcast (formerly Burning Glass Technologies) US Job Postings database. Lightcast aggregates the universe of online job postings across more than 50,000 sources (corporate career sites, government boards, third-party aggregators) and applies a proprietary deduplication pipeline. The release here covers calendar years 2010-2024, comprising 433.6 million unique postings after deduplication.

Each posting carries a structured set of fields: posting date, location (state, MSA, county, city), employer name, NAICS-4 industry code, Standard Occupational Classification (SOC), educational requirements, work-mode flag (remote / hybrid / on-site, populated from 2018 onward), internship flag, staffing-firm flag, and three categories of skills (specialized, software, common). Skills are extracted by Lightcast's NLP pipeline against an evolving taxonomy of approximately 30,000 distinct skill names.

The Lightcast data are licensed to subscribers under a separate agreement. This repository releases only county-year aggregates derived from the underlying micro data; replication from raw data requires a current Lightcast subscription.

## 2. Unit of observation

The panel is at the **county-year** level. Geography is the 5-digit FIPS county code; time is calendar year. The choice of county rather than a finer geography (city, ZIP) or coarser geography (state, MSA) reflects three considerations:

1. **Coverage stability.** County is the finest unit for which Lightcast geocoding is internally consistent across the full 2010-2024 window. City and ZIP codes are populated unevenly across years and across employer types.
2. **Population denominator.** Counties have well-defined, regularly updated population and labor-force denominators from the BEA, BLS, and Census, which lets users compute posting rates, per-capita measures, or labor-share normalizations without geographic reconciliation.
3. **Substantive theory.** County-year aligns with the unit used in the regional-branching and economic-complexity literature (Boschma 2017; Neffke et al. 2011; Hidalgo & Hausmann 2009; Balland et al. 2019).

The choice of annual rather than quarterly resolution reflects the small-cell problem at fine temporal resolution: many counties record fewer than 100 postings per quarter, which makes the diversity, complexity, and relatedness measures unstable.

## 3. Pipeline overview

The pipeline runs in three phases. See `code/README.md` for the pipeline diagram and `code/build_skill_counts.py`, `code/compute_skill_measures.py`, and `code/build_descriptive_export.py` for the implementation.

### Phase A: Streaming aggregation (`build_skill_counts.py`)

Phase A is a single streaming pass over the raw gzipped CSV shards. For each posting, the script:

1. Parses the `posted` date and assigns a calendar year.
2. Resolves the county FIPS from the `county` field. Postings with missing or invalid county are dropped.
3. Classifies the posting into one of four employer entity types using NAICS-4:
   - **University:** NAICS 6112-6117
   - **Federal or public lab:** NAICS 5417, 9271
   - **Government:** any NAICS in the 92xx range
   - **Corporate:** all remaining postings (the full private sector, regardless of NAICS-4 specificity)
4. Splits the three pipe-delimited skill columns (`specialized_skills_name`, `software_skills_name`, `common_skills_name`) into individual skill mentions.
5. Updates per-year accumulators of (county, skill, entity_type) mention counts and (county, posting characteristic) counts.

Phase A writes per-year checkpoint parquet files (Hive-partitioned at `year=YYYY`) and resumes from completed years on restart.

### Phase B: Derived measures (`compute_skill_measures.py`)

Phase B reads the Phase A checkpoints and computes the full battery of derived measures.

**Revealed Comparative Advantage (RCA).** For county *c*, year *t*, skill *s*:

```
RCA(c,t,s) = [mention_share of s in county c, year t]
             / [mention_share of s nationally in year t]
```

The numerator is the share of all skill mentions in county *c* during year *t* that are skill *s*; the denominator is the corresponding national share. RCA > 1 indicates that the county over-specializes in the skill relative to the nation. This is the standard Balassa formulation adapted from international trade.

**Skill-skill relatedness.** Following Hidalgo et al. (2007), the relatedness between two skills *s* and *s'* in year *t* is the conditional probability that a randomly chosen county has RCA > 1 in *s'*, given that it has RCA > 1 in *s* (and vice versa; the symmetric minimum is taken). The result is a year-specific |S| × |S| symmetric matrix.

**Balland skill density.** For each county *c*, year *t*, the average relatedness of *non-RCA* skills to the county's *RCA > 1* skills. This is the Balland et al. (2019) "relatedness density" measure; it predicts which skills a county is likely to acquire next.

**Neffke skill coherence.** For each county *c*, year *t*, the average pairwise relatedness *among* the county's RCA > 1 skills. High coherence indicates a tightly clustered specialization profile (Neffke et al. 2011).

**Economic Complexity Index (ECI).** Computed by the Hidalgo-Hausmann method of reflections: an iterative process that alternates between county-level diversification (count of RCA > 1 skills) and skill-level ubiquity (count of counties with RCA > 1 in the skill). Twenty iterations; the final county-level value is standardized to mean 0, standard deviation 1 within each year. Adapted from countries × products to counties × skills.

**Tacchella fitness-complexity.** A non-linear alternative to ECI (Tacchella et al. 2012). County fitness scales linearly with the sum of skill complexities; skill complexity scales inversely with the harmonic mean of fitness across counties that have RCA > 1 in the skill. Fifty iterations. Released as `fitness`; the column is numerically unstable for very diversified or very specialized counties and should be log-transformed or clipped before downstream use.

**Average centrality.** For each county *c*, year *t*, the mean (year-specific) eigenvector centrality of the county's RCA > 1 skills in the skill-space network. Captures whether the county specializes in "core" connected skills or "peripheral" isolated skills.

**Year-over-year dynamics.**
- `churning_entries`: count of skills with RCA > 1 in year *t* but not year *t-1*
- `churning_exits`: count of skills with RCA > 1 in year *t-1* but not year *t*
- `churning_net`: `churning_entries - churning_exits`
- `skill_cosine_distance`: 1 - cos(skill_freq_vec(c, t-1), skill_freq_vec(c, t)), capturing total structural change in the demand profile

**Entity-type specialization breadth.** For each of the four entity types, the count of skills with entity-specific RCA > 1 (`{type}_n_rca_skills`). Entity-type-specific RCA computes the numerator using only postings from that entity type while keeping the national-share denominator unchanged.

**Employer-pair skill similarity (group J).** For each of the three entity-type pairs (university vs corporate, federal/public lab vs corporate, university vs federal/public lab), six similarity measures (cosine, Jaccard, Hidalgo proximity, weighted RCA overlap, directional gap count, directional gap relatedness) are computed between the two entity types' skill-frequency vectors within each county-year. Each measure is reported over all skills and separately over specialized, software, and common skill subsets.

**Per-employer-type dynamics (group K).** For each of the four entity types, churning entries, exits, net change, and cosine distance are computed within the entity type's own skill pool in parallel to the aggregate group-H measures.

### Phase C: Public-release export (`build_descriptive_export.py`)

Generates the data dictionary, codebook, summary statistics, and yearly summary that accompany the 129-column Phase B output. The panel itself is the direct Phase B output and requires no additional subsetting.

## 4. Known limitations

The public README documents the most consequential caveats:

- **NAICS-classification quality within the corporate category.** A substantial share of corporate postings have NAICS-4 = 9999 (Lightcast was unable to assign a specific industry). This share falls from approximately 40% in 2010 to 15% in 2024 as Lightcast's firm-identification pipeline matures. These postings are included in `n_corporate` and in the aggregate skill measures. Early-year corporate-specific RCA breadth (group I) is correspondingly biased toward larger, identifiable firms.
- **2017-2018 Lightcast coverage step-up.** National posting volume jumps by approximately 26% between 2017 and 2018 because of a Lightcast source expansion. Use shares rather than levels, or include county fixed effects, when comparing across this boundary.
- **Cosine distance noisy below 50 postings.** Apply a posting threshold for causal-inference work using `skill_cosine_distance`.
- **State-level FIPS codes (ending in 999).** Postings that Lightcast could match to a state but not a specific county are assigned to a state-level FIPS ending in 999. For county-level analyses, drop with `(county % 1000) != 999`.
- **Fitness-complexity instability.** The Tacchella fitness column should be log-transformed or clipped before downstream use.

## 5. Reproducibility

The pipeline is deterministic given the same input data. Three independent re-runs during development produced bit-identical output (within parquet write-order noise). The full panel can be rebuilt from raw Lightcast Main data using the scripts in `code/`, given a Lightcast subscription and access to an HPC cluster with at least 200 GB of memory.

## 6. Selected references

- Balassa, B. (1965). Trade liberalisation and "revealed" comparative advantage. *The Manchester School*, 33(2), 99-123.
- Balland, P.-A., Boschma, R., Crespo, J., & Rigby, D. L. (2019). Smart specialization policy in the European Union. *Research Policy*, 48(1), 30-39.
- Boschma, R. (2017). Relatedness as driver of regional diversification: A research agenda. *Regional Studies*, 51(3), 351-364.
- Hidalgo, C. A., Klinger, B., Barabási, A.-L., & Hausmann, R. (2007). The product space conditions the development of nations. *Science*, 317(5837), 482-487.
- Hidalgo, C. A., & Hausmann, R. (2009). The building blocks of economic complexity. *PNAS*, 106(26), 10570-10575.
- Neffke, F., Henning, M., & Boschma, R. (2011). How do regions diversify over time? *Economic Geography*, 87(3), 237-265.
- Tacchella, A., Cristelli, M., Caldarelli, G., Gabrielli, A., & Pietronero, L. (2012). A new metrics for countries' fitness and product complexity. *Scientific Reports*, 2, 723.
