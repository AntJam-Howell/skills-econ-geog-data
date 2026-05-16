#!/bin/bash
#SBATCH --job-name=ls_phaseb_v2
#SBATCH --partition=public
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=/data/ajhowel5/LightcastSkills/logs/%x_%j.out
#SBATCH --error=/data/ajhowel5/LightcastSkills/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ajhowel5@asu.edu

# ==============================================================================
# Phase B v2: Employer-type RCA + Institution-type RCA + Dynamics
#
# Reads Phase A v2 employer_skill checkpoints (with naics2/naics4/skill_type)
# and computes employer-type-specific measures. Updates county_year_panel.
#
# Per-year processing — peak memory ~60-80GB when handling biggest year (2022)
# Expected runtime: 1-2 hours
#
# This SLURM file is a Sol-specific template. On any other HPC environment,
# update both the SBATCH directives (--output, --error, --mail-user, --partition)
# AND the LIGHTCAST_DATA_DIR export below.
# ==============================================================================

# Path configuration consumed by compute_phaseb_v2.py.
# Default matches the Sol layout; override here for other environments.
export LIGHTCAST_DATA_DIR="/data/ajhowel5/LightcastSkills/processed"

echo "============================================"
echo "  Phase B v2: Employer RCA + Dynamics"
echo "  Job started: $(date)"
echo "  Node: $(hostname)"
echo "  LIGHTCAST_DATA_DIR=${LIGHTCAST_DATA_DIR}"
echo "============================================"
echo ""

cd /data/ajhowel5/LightcastSkills
source .venv/bin/activate

python3 -c "import pandas, numpy; print('OK: pandas', pandas.__version__, 'numpy', numpy.__version__)"
echo ""

# Verify Phase A v2 checkpoints exist
echo "Checking Phase A v2 checkpoints..."
MISSING=0
for y in $(seq 2010 2024); do
    if [ ! -f "${LIGHTCAST_DATA_DIR}/intermediate/scan/year=$y/_SUCCESS" ]; then
        echo "  MISSING: year=$y"
        MISSING=$((MISSING + 1))
    fi
done
echo "  Missing: $MISSING / 15 years"
if [ $MISSING -gt 0 ]; then
    echo "ERROR: Phase A v2 incomplete — aborting"
    exit 1
fi
echo ""

python3 scripts/compute_phaseb_v2.py

echo ""
echo "============================================"
echo "  Job finished: $(date)"
echo "============================================"
