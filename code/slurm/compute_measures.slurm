#!/bin/bash
#SBATCH --job-name=ls_compute_measures
#SBATCH --partition=public
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=200G
#SBATCH --time=24:00:00
#SBATCH --output=/data/ajhowel5/LightcastSkills/logs/%x_%j.out
#SBATCH --error=/data/ajhowel5/LightcastSkills/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ajhowel5@asu.edu

# ==============================================================================
# Phase B: Compute Skill Measures
#
# Reads Phase A checkpoints, computes RCA, relatedness, density, complexity,
# employer-type similarity, dynamics. Writes final panels.
#
# Expected runtime: 30-60 min (up to 2 hr for large skill vocabularies)
# Wall time: 4:00:00 (generous margin)
# ==============================================================================

echo "============================================"
echo "  Phase B: Compute Skill Measures"
echo "  Job started: $(date)"
echo "  Node: $(hostname)"
echo "============================================"
echo ""

cd /data/ajhowel5/LightcastSkills
source .venv/bin/activate

python3 -c "import pandas, numpy; print('OK: pandas', pandas.__version__, 'numpy', numpy.__version__)"
echo ""

# Verify Phase A checkpoints exist
echo "Checking Phase A checkpoints..."
COMPLETE=0
MISSING=0
for y in $(seq 2010 2024); do
    if [ -f "processed/intermediate/scan/year=$y/_SUCCESS" ]; then
        COMPLETE=$((COMPLETE + 1))
    else
        echo "  MISSING: year=$y"
        MISSING=$((MISSING + 1))
    fi
done
echo "  Complete: $COMPLETE / 15 years"
if [ $MISSING -gt 0 ]; then
    echo "  WARNING: $MISSING years missing — Phase B will process available years only"
fi
echo ""

python3 scripts/compute_skill_measures.py

echo ""
echo "============================================"
echo "  Job finished: $(date)"
echo "============================================"
