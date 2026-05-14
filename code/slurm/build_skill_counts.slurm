#!/bin/bash
#SBATCH --job-name=ls_build_counts
#SBATCH --partition=public
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --output=/data/ajhowel5/LightcastSkills/logs/%x_%j.out
#SBATCH --error=/data/ajhowel5/LightcastSkills/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ajhowel5@asu.edu

# ==============================================================================
# Phase A: Build Skill Counts
#
# Single-pass scan of 466M Lightcast postings (2010-2024).
# Splits skills, classifies employer type, aggregates to
# (county, year, skill, employer_type) counts.
# Checkpoints per year — safe to resubmit if wall time hit.
#
# Expected runtime: 8-12 hours for full 2010-2024 scan
# Wall time: 48:00:00 (safer margin — first attempt timed out at 24h with 12/15 years done)
# Script skips completed years via _SUCCESS markers; resubmit is safe.
# ==============================================================================

echo "============================================"
echo "  Phase A: Build Skill Counts"
echo "  Job started: $(date)"
echo "  Node: $(hostname)"
echo "  CPUs: $SLURM_CPUS_PER_TASK"
echo "  Memory: ${SLURM_MEM_PER_NODE}MB"
echo "============================================"
echo ""

cd /data/ajhowel5/LightcastSkills
source .venv/bin/activate

python3 -c "import pandas, pyarrow, numpy; print('OK: pandas', pandas.__version__, 'pyarrow', pyarrow.__version__, 'numpy', numpy.__version__)"

echo ""
echo "Checking raw data..."
for y in 2010 2015 2020 2024; do
    [ -d /data/ajhowel5/Lightcast/Main/$y ] && echo "  $y: OK" || echo "  $y: MISSING"
done
echo ""

python3 scripts/build_skill_counts.py

echo ""
echo "============================================"
echo "  Job finished: $(date)"
echo "============================================"
