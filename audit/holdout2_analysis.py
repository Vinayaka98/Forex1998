#!/usr/bin/env python3
"""
Holdout #2 Analysis — Preregistered Independent Confirmation Test
=================================================================
This script implements the analysis protocol from docs/HOLDOUT2_PREREGISTRATION.md.

IMPORTANT: Do NOT modify this script after viewing Holdout #2 results.
The methodology was locked before data collection (see preregistration commit).

Protocol:
  Step 1: Analyze Holdout #2 data BY ITSELF (standalone)
  Step 2: Optionally combine with prior OOS for estimation (clearly labeled)

Preregistered hypotheses:
  Primary:   V3 after-cost expectancy on all Holdout #2 pairs is positive
  Secondary: EUR pairs expectancy > non-EUR pairs expectancy

Validation:
  - Standard block bootstrap CI (individual trades)
  - Temporal clustering bootstrap CI (calendar-day clusters)

Random seed: 42 (same as full_audit.py for reproducibility)

Usage:
  python holdout2_analysis.py --data-dir /path/to/holdout2/csvs
"""
import csv, os, math, random, argparse, sys
from datetime import datetime, timezone
from collections import defaultdict

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

parser = argparse.ArgumentParser(description="Holdout #2 Preregistered Analysis")
parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help="Directory containing Holdout #2 CSV files (default: ../data/)")
_args, _ = parser.parse_known_args()
DATA_DIR = os.path.abspath(_args.data_dir)

# Pair-specific spreads from preregistration (realistic scenario, pips)
PAIR_SPREADS = {
    "EURUSD": 1.0, "EURGBP": 1.5, "EURAUD": 2.0, "EURCAD": 2.0,
    "EURNZD": 2.5, "EURCHF": 2.0, "EURJPY": 1.5, "USDCAD": 1.5,
    "NZDUSD": 1.5, "AUDUSD": 1.0, "USDJPY": 1.0, "GBPUSD": 1.5,
    "AUDCAD": 2.0, "AUDNZD": 2.5, "AUDCHF": 2.0, "AUDJPY": 2.0,
}
COMMISSION_PIPS = 0.7       # $7/100k RT
SLIPPAGE_PIPS = 0.5         # conservative
PESSIMISTIC_SPREAD_ADD = 1.0
PESSIMISTIC_COMMISSION = 1.0
PESSIMISTIC_SLIPPAGE = 1.0

# TODO: Populate when Holdout #2 CSVs are available
# Format: "LABEL": ("filename.csv", "TP column name", "dataset_tag")
HOLDOUT2_FILES = {
    # Example:
    # "EURUSD_H2": ("OANDA_EURUSD_240.csv", "Active TP2", "HOLDOUT2"),
}


def per_trade_cost_r(stop_pips, pair, pessimistic=False):
    """Compute cost in R-multiples for a specific trade."""
    spread = PAIR_SPREADS.get(pair, 2.0)
    comm = COMMISSION_PIPS
    slip = SLIPPAGE_PIPS
    if pessimistic:
        spread += PESSIMISTIC_SPREAD_ADD
        comm = PESSIMISTIC_COMMISSION
        slip = PESSIMISTIC_SLIPPAGE
    return (spread + comm + slip) / stop_pips


def block_bootstrap(trade_rs, block_size, n_target, n_sims=10000):
    """Resample trade R-values in blocks with replacement."""
    n = len(trade_rs)
    if n == 0:
        return []
    results = []
    for _ in range(n_sims):
        seq = []
        while len(seq) < n_target:
            start = random.randint(0, n - block_size)
            seq.extend(trade_rs[start:start + block_size])
        seq = seq[:n_target]
        results.append(sum(seq) / len(seq))
    return sorted(results)


def cluster_bootstrap(trades_with_dates, n_sims=10000):
    """
    Temporal clustering bootstrap — cluster trades by calendar day,
    resample clusters with replacement, compute mean expectancy.
    """
    clusters = defaultdict(list)
    for t in trades_with_dates:
        day_key = t['date'].strftime('%Y-%m-%d')
        clusters[day_key].append(t['r'])
    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)
    if n_clusters == 0:
        return []
    results = []
    for _ in range(n_sims):
        sampled_rs = []
        for _ in range(n_clusters):
            c = cluster_list[random.randint(0, n_clusters - 1)]
            sampled_rs.extend(c)
        results.append(sum(sampled_rs) / len(sampled_rs) if sampled_rs else 0)
    return sorted(results)


def bootstrap_ci(sorted_results, confidence=0.90):
    """Extract confidence interval from sorted bootstrap results."""
    if not sorted_results:
        return (0, 0)
    n = len(sorted_results)
    lo = int(n * (1 - confidence) / 2)
    hi = int(n * (1 + confidence) / 2) - 1
    return (sorted_results[lo], sorted_results[hi])


if __name__ == "__main__":
    if not HOLDOUT2_FILES:
        print("=" * 60)
        print("Holdout #2 Analysis — AWAITING DATA")
        print("=" * 60)
        print()
        print(f"Random seed: {RANDOM_SEED}")
        print(f"Data directory: {DATA_DIR}")
        print()
        print("Populate HOLDOUT2_FILES dict with CSV filenames,")
        print("then re-run this script.")
        print()
        print("See docs/HOLDOUT2_PREREGISTRATION.md for the full protocol.")
        sys.exit(0)

    # TODO: Implement when data is available:
    # 1. Load all CSVs, detect trades
    # 2. Compute per-trade costs using per_trade_cost_r()
    # 3. Report standalone Holdout #2 metrics
    # 4. Block bootstrap CI (sizes 3, 5, 8, 10, 15)
    # 5. Cluster bootstrap CI (calendar-day clusters)
    # 6. EUR vs non-EUR comparison
    # 7. Classify result per preregistered framework
