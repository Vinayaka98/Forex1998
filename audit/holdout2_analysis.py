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
from collections import defaultdict, OrderedDict

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

parser = argparse.ArgumentParser(description="Holdout #2 Preregistered Analysis")
parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help="Directory containing Holdout #2 CSV files (default: ../data/)")
_args, _ = parser.parse_known_args()
DATA_DIR = os.path.abspath(_args.data_dir)

PAIR_SPREADS = {
    "EURUSD": 1.0, "EURGBP": 1.5, "EURAUD": 2.0, "EURCAD": 2.0,
    "EURNZD": 2.5, "EURCHF": 2.0, "EURJPY": 1.5, "USDCAD": 1.5,
    "NZDUSD": 1.5, "AUDUSD": 1.0, "USDJPY": 1.0, "GBPUSD": 1.5,
    "AUDCAD": 2.0, "AUDNZD": 2.5, "AUDCHF": 2.0, "AUDJPY": 2.0,
}
COMMISSION_PIPS = 0.7
SLIPPAGE_PIPS = 0.5
PESSIMISTIC_SPREAD_ADD = 1.0
PESSIMISTIC_COMMISSION = 1.0
PESSIMISTIC_SLIPPAGE = 1.0

HOLDOUT2_FILES = {
    "AUDUSD_H2": ("OANDA_AUDUSD_240.csv", "Active TP2"),
    "AUDJPY_H2": ("OANDA_AUDJPY_240.csv", "Active TP2"),
    "AUDCHF_H2": ("OANDA_AUDCHF_240.csv", "Active TP2"),
    "AUDNZD_H2": ("OANDA_AUDNZD_240.csv", "Active TP2"),
    "AUDCAD_H2": ("OANDA_AUDCAD_240.csv", "Active TP2"),
}

N_SIMS = 10000
W = '=' * 100
D = '-' * 100


def per_trade_cost_r(stop_pips, pair, pessimistic=False):
    spread = PAIR_SPREADS.get(pair, 2.0)
    comm = COMMISSION_PIPS
    slip = SLIPPAGE_PIPS
    if pessimistic:
        spread += PESSIMISTIC_SPREAD_ADD
        comm = PESSIMISTIC_COMMISSION
        slip = PESSIMISTIC_SLIPPAGE
    return (spread + comm + slip) / stop_pips


def load_csv(fp, tp_col="Active TP2"):
    rows = []
    with open(fp) as f:
        for r in csv.DictReader(f):
            row = {
                'time': int(r['time']),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'sl': float(r['Active SL']) if r.get('Active SL', '').strip() else None,
            }
            for col in [tp_col, 'Active TP2', 'Active TP']:
                if col in r and r[col].strip():
                    row['tp'] = float(r[col]); break
            else:
                row['tp'] = None
            rows.append(row)
    return rows


def compute_atr(rows, p=14):
    a = [0.0] * len(rows)
    for i in range(len(rows)):
        if i == 0:
            a[i] = rows[i]['high'] - rows[i]['low']
        else:
            tr = max(rows[i]['high'] - rows[i]['low'],
                     abs(rows[i]['high'] - rows[i-1]['close']),
                     abs(rows[i]['low'] - rows[i-1]['close']))
            a[i] = (a[i-1] * (min(i, p) - 1) + tr) / min(i, p) if i < p else (a[i-1] * (p - 1) + tr) / p
    return a


def compute_adx(rows, p=14):
    n = len(rows); adx = [0.0]*n; pdm = [0.0]*n; mdm = [0.0]*n; tr = [0.0]*n
    for i in range(1, n):
        u = rows[i]['high'] - rows[i-1]['high']; d = rows[i-1]['low'] - rows[i]['low']
        pdm[i] = u if u > d and u > 0 else 0; mdm[i] = d if d > u and d > 0 else 0
        tr[i] = max(rows[i]['high'] - rows[i]['low'],
                     abs(rows[i]['high'] - rows[i-1]['close']),
                     abs(rows[i]['low'] - rows[i-1]['close']))
    st = [0.0]*n; sp = [0.0]*n; sm = [0.0]*n
    for i in range(1, min(p+1, n)):
        st[p] += tr[i]; sp[p] += pdm[i]; sm[p] += mdm[i]
    for i in range(p+1, n):
        st[i] = st[i-1] - st[i-1]/p + tr[i]
        sp[i] = sp[i-1] - sp[i-1]/p + pdm[i]
        sm[i] = sm[i-1] - sm[i-1]/p + mdm[i]
    dx = [0.0]*n
    for i in range(p, n):
        if st[i] > 0:
            pi_ = 100 * sp[i] / st[i]; mi_ = 100 * sm[i] / st[i]
            if pi_ + mi_ > 0:
                dx[i] = 100 * abs(pi_ - mi_) / (pi_ + mi_)
    for i in range(p*2, n):
        adx[i] = (sum(dx[p:p*2]) / p) if i == p*2 else (adx[i-1] * (p-1) + dx[i]) / p
    return adx


def percentrank(series, idx, length):
    if idx < length:
        return 50.0
    val = series[idx]
    return sum(1 for j in range(idx - length, idx) if series[j] < val) / length * 100.0


def extract_trades(pair, fp, tp_col):
    rows = load_csv(fp, tp_col)
    atr = compute_atr(rows)
    adx = compute_adx(rows)
    trades = []; in_trade = False; prev_sl = None
    entry_bar = ep = sd = itp = 0
    rmfe = rmae = 0.0; bdata = []
    current_sl = current_tp = 0.0

    for i, bar in enumerate(rows):
        sl = bar['sl']; tp = bar['tp']
        is_new = sl is not None and prev_sl is None
        if in_trade:
            if sl is not None:
                current_sl = sl
            bn = i - entry_bar
            bhr = (bar['high'] - ep) / sd; blr = (bar['low'] - ep) / sd; bcr = (bar['close'] - ep) / sd
            rmfe = max(rmfe, bhr); rmae = max(rmae, -blr)
            bdata.append({'bar': bn, 'high_r': bhr, 'low_r': blr, 'close_r': bcr})
            xp = None; xreason = ""
            if bar['low'] <= current_sl:
                xp = current_sl; xreason = "SL"
            elif current_tp > 0 and bar['high'] >= current_tp:
                xp = current_tp; xreason = "TP"
            elif sl is None:
                xp = bar['close']; xreason = "IND"
            if xp is not None:
                rr = (xp - ep) / sd
                if xreason == "SL" and rr < -1.0:
                    rr = -1.0
                if xreason == "TP":
                    tpr = abs(itp - ep) / sd; rr = min(rr, tpr)
                edt = datetime.fromtimestamp(rows[entry_bar]['time'], tz=timezone.utc)
                pair_name = pair.split('_')[0] if '_' in pair else pair
                stop_pips = sd * 10000 if 'JPY' not in pair_name else sd * 100
                trades.append({
                    'pair': pair_name,
                    'label': pair, 'dir': 'BUY',
                    'entry_time': rows[entry_bar]['time'],
                    'entry_dt': edt,
                    'ep': ep, 'sd': sd,
                    'itp_r': abs(itp - ep) / sd if itp > 0 and sd > 0 else 0,
                    'atr': atr[entry_bar], 'adx': adx[entry_bar],
                    'atr_pctrank': percentrank(atr, entry_bar, 100),
                    'bd': bdata[:], 'orig_r': rr, 'orig_bars': len(bdata),
                    'orig_reason': xreason, 'orig_mfe': rmfe, 'orig_mae': rmae,
                    'entry_hour': edt.hour, 'entry_dow': edt.weekday(),
                    'stop_pips': stop_pips,
                })
                in_trade = False
        if not in_trade and is_new:
            entry_bar = i; ep = bar['close']; isl = sl; itp = tp if tp else 0
            current_sl = sl; current_tp = itp
            sd = abs(ep - isl)
            if sd == 0:
                sd = 0.0001
            if isl < ep:
                rmfe = 0.0; rmae = 0.0; bdata = []
                in_trade = True
        prev_sl = sl
    return trades


def apply_v2(trades, atr_thr=66, adx_thr=18.0, excl_pairs=None):
    if excl_pairs is None:
        excl_pairs = {"EURAUD"}
    return [t for t in trades
            if t['pair'] not in excl_pairs
            and not (t['atr_pctrank'] > atr_thr and t['adx'] < adx_thr)]


def sim_stale(trade, sb=8, sm=0.5):
    bd = trade['bd']
    if not bd:
        return trade['orig_r'], trade['orig_bars'], trade['orig_reason']
    mx = 0.0
    for b in bd:
        mx = max(mx, b['high_r'])
        if b['bar'] >= sb and mx < sm:
            return b['close_r'], b['bar'], "STALE"
    return trade['orig_r'], trade['orig_bars'], trade['orig_reason']


def final_r(t, sb=8, sm=0.5):
    r, _, _ = sim_stale(t, sb, sm)
    return r


def stats(rs):
    if not rs:
        return {'n': 0, 'R': 0, 'wr': 0, 'pf': 0, 'exp': 0, 'mdd': 0, 'rdd': 0, 'aw': 0, 'al': 0, 'sharpe': 0}
    n = len(rs); tr = sum(rs)
    w = [r for r in rs if r >= 0.1]; l = [r for r in rs if r <= -0.1]
    gw = sum(w); gl = abs(sum(l))
    pf = gw / gl if gl > 0 else 99.9
    eq = 0; pk = 0; mdd = 0
    for r in rs:
        eq += r; pk = max(pk, eq); mdd = max(mdd, pk - eq)
    aw = gw / len(w) if w else 0; al = gl / len(l) if l else 0
    mean = tr / n; var = sum((r - mean)**2 for r in rs) / n if n > 1 else 0
    std = math.sqrt(var) if var > 0 else 0.001
    sharpe = mean / std * math.sqrt(n) if std > 0 else 0
    return {'n': n, 'R': tr, 'wr': len(w) / n * 100, 'pf': pf, 'exp': tr / n,
            'mdd': mdd, 'aw': aw, 'al': al, 'rdd': tr / mdd if mdd > 0 else 0, 'sharpe': sharpe}


def print_stats(label, s, indent=2):
    sp = ' ' * indent
    print(f"{sp}{label}: {s['n']}t  WR={s['wr']:.1f}%  PF={s['pf']:.2f}  R={s['R']:+.1f}  "
          f"Exp={s['exp']:+.3f}  MaxDD={s['mdd']:.1f}  R/DD={s['rdd']:.2f}  "
          f"AvgW={s['aw']:.2f}  AvgL={s['al']:.2f}  Sharpe={s['sharpe']:.2f}")


def block_bootstrap_ci(trade_rs, block_size, n_target, n_sims=N_SIMS):
    n = len(trade_rs)
    if n == 0:
        return []
    results = []
    for _ in range(n_sims):
        seq = []
        while len(seq) < n_target:
            start = random.randint(0, n - 1)
            for j in range(block_size):
                if len(seq) >= n_target:
                    break
                seq.append(trade_rs[(start + j) % n])
        results.append(sum(seq) / len(seq))
    return sorted(results)


def cluster_bootstrap(trades_with_dates, n_sims=N_SIMS):
    clusters = defaultdict(list)
    for t in trades_with_dates:
        day_key = t['entry_dt'].strftime('%Y-%m-%d')
        clusters[day_key].append(t['net_r'])
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


def ci_from_sorted(sorted_results, confidence=0.90):
    if not sorted_results:
        return (0, 0)
    n = len(sorted_results)
    lo = int(n * (1 - confidence) / 2)
    hi = int(n * (1 + confidence) / 2) - 1
    return (sorted_results[lo], sorted_results[hi])


# ══════════════════════════════════════════════════════════
#  MAIN ANALYSIS
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not HOLDOUT2_FILES:
        print("=" * 60)
        print("Holdout #2 Analysis — AWAITING DATA")
        print("=" * 60)
        print(f"\nRandom seed: {RANDOM_SEED}")
        print(f"Data directory: {DATA_DIR}")
        print("\nPopulate HOLDOUT2_FILES dict with CSV filenames,")
        print("then re-run this script.")
        sys.exit(0)

    print(f"\n{W}")
    print("  HOLDOUT #2 — PREREGISTERED INDEPENDENT CONFIRMATION TEST")
    print(f"  Protocol: docs/HOLDOUT2_PREREGISTRATION.md")
    print(f"  Random seed: {RANDOM_SEED}")
    print(W)

    # ── SECTION 0: DATA LOADING ──
    print(f"\n{W}")
    print("  SECTION 0: DATA LOADING")
    print(W)

    all_trades = []
    missing = []
    for label, (fname, tp_col) in sorted(HOLDOUT2_FILES.items()):
        fp = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fp):
            print(f"  MISSING: {label} ({fname})")
            missing.append(label)
            continue
        trades = extract_trades(label, fp, tp_col)
        print(f"  {label:>18}: {len(trades):>3} raw BUY trades")
        all_trades.extend(trades)

    if missing:
        print(f"\n  WARNING: {len(missing)} file(s) missing: {', '.join(missing)}")

    if not all_trades:
        print("\n  ERROR: No trades found in any file. Check CSV format.")
        sys.exit(1)

    all_trades.sort(key=lambda t: t['entry_time'])
    print(f"\n  Total raw BUY trades: {len(all_trades)}")

    # Apply V2 gates (frozen: ATR %ile > 66 AND ADX < 18 → filter out)
    v2 = apply_v2(all_trades)
    print(f"  After V2 filter: {len(v2)} trades")
    print(f"  Filtered out: {len(all_trades) - len(v2)} trades")

    # Apply stale exit (frozen: bar >= 8, MFE < 0.5R)
    for t in v2:
        t['final_r'] = final_r(t)
        t['cost_r'] = per_trade_cost_r(t['stop_pips'], t['pair'], pessimistic=False)
        t['cost_r_pess'] = per_trade_cost_r(t['stop_pips'], t['pair'], pessimistic=True)
        t['net_r'] = t['final_r'] - t['cost_r']
        t['net_r_pess'] = t['final_r'] - t['cost_r_pess']

    # Date range
    first_dt = min(t['entry_dt'] for t in v2)
    last_dt = max(t['entry_dt'] for t in v2)
    print(f"  Date range: {first_dt.strftime('%Y-%m-%d %H:%M')} to {last_dt.strftime('%Y-%m-%d %H:%M')} UTC")

    # Per-pair summary
    pairs = sorted(set(t['pair'] for t in v2))
    print(f"  Pairs with trades: {', '.join(pairs)}")
    eur_trades = [t for t in v2 if t['pair'].startswith('EUR')]
    non_eur_trades = [t for t in v2 if not t['pair'].startswith('EUR')]
    print(f"  EUR trades: {len(eur_trades)}")
    print(f"  Non-EUR trades: {len(non_eur_trades)}")

    # Trade count check
    n_trades = len(v2)
    if n_trades < 300:
        print(f"\n  NOTE: {n_trades} trades < 300 minimum per stopping rule.")
        print(f"  Per protocol: extend by 6 calendar months and re-export.")

    # ══════════════════════════════════════════════════════════
    #  SECTION 1: HOLDOUT #2 STANDALONE — GROSS PERFORMANCE
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 1: HOLDOUT #2 STANDALONE — Performance Metrics")
    print(f"  (This is the CLEAN, INDEPENDENT test — analyzed BY ITSELF)")
    print(W)

    rs_gross = [t['final_r'] for t in v2]
    rs_net = [t['net_r'] for t in v2]
    rs_net_pess = [t['net_r_pess'] for t in v2]

    s_gross = stats(rs_gross)
    s_net = stats(rs_net)
    s_pess = stats(rs_net_pess)

    print(f"\n  All Holdout #2 trades ({n_trades} trades):")
    print_stats("Gross (no costs)", s_gross)
    print_stats("After realistic costs", s_net)
    print_stats("After pessimistic costs", s_pess)

    avg_cost_r = sum(t['cost_r'] for t in v2) / n_trades
    avg_cost_pips = sum(t['cost_r'] * t['stop_pips'] for t in v2) / n_trades
    avg_stop = sum(t['stop_pips'] for t in v2) / n_trades
    print(f"\n  Cost model:")
    print(f"    Average stop distance: {avg_stop:.1f} pips")
    print(f"    Average cost (realistic): {avg_cost_r:.4f}R ({avg_cost_pips:.1f} pips)")
    print(f"    Total cost deducted: {sum(t['cost_r'] for t in v2):.1f}R")

    # Per-pair breakdown
    print(f"\n  Per-pair breakdown (after realistic costs):")
    print(f"  {'Pair':>10}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'DD':>5}  {'AvgStop':>8}")
    print(f"  {'─'*10}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*8}")
    for pair in pairs:
        pt = [t for t in v2 if t['pair'] == pair]
        rs_p = [t['net_r'] for t in pt]
        s_p = stats(rs_p)
        avg_stp = sum(t['stop_pips'] for t in pt) / len(pt)
        print(f"  {pair:>10}  {s_p['n']:>4}  {s_p['wr']:>5.1f}%  {s_p['pf']:>5.2f}  "
              f"{s_p['R']:>+6.1f}  {s_p['exp']:>+6.3f}  {s_p['mdd']:>5.1f}  {avg_stp:>7.1f}p")

    # Exit reason breakdown
    stale_count = sum(1 for t in v2 if sim_stale(t)[2] == "STALE")
    sl_count = sum(1 for t in v2 if sim_stale(t)[2] == "SL")
    tp_count = sum(1 for t in v2 if sim_stale(t)[2] == "TP")
    ind_count = sum(1 for t in v2 if sim_stale(t)[2] == "IND")
    print(f"\n  Exit reasons: SL={sl_count}  TP={tp_count}  STALE={stale_count}  IND={ind_count}")

    # ══════════════════════════════════════════════════════════
    #  SECTION 2: PRIMARY HYPOTHESIS — System-wide expectancy
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 2: PRIMARY HYPOTHESIS — After-cost expectancy positive?")
    print(W)

    exp_net = s_net['exp']
    print(f"\n  Observed after-cost expectancy: {exp_net:+.4f} R/trade")
    print(f"  Total after-cost R: {s_net['R']:+.1f} over {n_trades} trades")

    # Block bootstrap CI — multiple block sizes as preregistered
    print(f"\n  ── Block Bootstrap 90% CI for Expectancy ──")
    print(f"  {'Block':>6}  {'90% CI':>24}  {'Median':>8}  {'% > 0':>7}")
    print(f"  {'─'*6}  {'─'*24}  {'─'*8}  {'─'*7}")
    for bs in [3, 5, 8, 10, 15]:
        boot = block_bootstrap_ci(rs_net, bs, n_trades)
        lo, hi = ci_from_sorted(boot, 0.90)
        med = boot[len(boot) // 2]
        ppos = sum(1 for e in boot if e > 0) / len(boot) * 100
        mark = " <-- primary" if bs == 5 else ""
        print(f"  {bs:>6}  [{lo:+.4f}, {hi:+.4f}]  {med:+.4f}  {ppos:>5.1f}%{mark}")

    # Cluster bootstrap (calendar-day clusters — preregistered)
    print(f"\n  ── Temporal Clustering Bootstrap 90% CI ──")
    print(f"  (Clusters trades by calendar day; resamples clusters, not trades)")

    clusters = defaultdict(list)
    for t in v2:
        day_key = t['entry_dt'].strftime('%Y-%m-%d')
        clusters[day_key].append(t)
    n_clusters = len(clusters)
    avg_cluster_size = n_trades / n_clusters if n_clusters > 0 else 0
    print(f"  Calendar-day clusters: {n_clusters}")
    print(f"  Average trades per cluster: {avg_cluster_size:.1f}")

    cluster_boot = cluster_bootstrap(v2)
    c_lo, c_hi = ci_from_sorted(cluster_boot, 0.90)
    c_med = cluster_boot[len(cluster_boot) // 2]
    c_ppos = sum(1 for e in cluster_boot if e > 0) / len(cluster_boot) * 100

    print(f"  Cluster bootstrap 90% CI: [{c_lo:+.4f}, {c_hi:+.4f}]")
    print(f"  Cluster bootstrap median: {c_med:+.4f}")
    print(f"  Cluster resamples > 0: {c_ppos:.1f}%")

    # Primary hypothesis verdict
    # Use block-5 as primary (consistent with prior audit)
    boot_5 = block_bootstrap_ci(rs_net, 5, n_trades)
    lo_5, hi_5 = ci_from_sorted(boot_5, 0.90)
    ppos_5 = sum(1 for e in boot_5 if e > 0) / len(boot_5) * 100

    print(f"\n  ── PRIMARY HYPOTHESIS RESULT ──")
    print(f"  Observed expectancy:    {exp_net:+.4f} R/trade")
    print(f"  Block-5 90% CI:         [{lo_5:+.4f}, {hi_5:+.4f}]")
    print(f"  Cluster 90% CI:         [{c_lo:+.4f}, {c_hi:+.4f}]")

    if lo_5 > 0 and c_lo > 0:
        print(f"  RESULT: BOTH CIs entirely positive — STRONG CONFIRMATION")
        primary_result = "STRONG_CONFIRM"
    elif exp_net > 0 and (lo_5 > 0 or c_lo > 0):
        print(f"  RESULT: At least one CI entirely positive — MODERATE CONFIRMATION")
        primary_result = "MODERATE_CONFIRM"
    elif exp_net > 0 and ppos_5 > 50:
        if c_lo < 0:
            print(f"  RESULT: Positive expectancy but cluster CI crosses zero — PROMISING BUT INCONCLUSIVE")
        else:
            print(f"  RESULT: Positive expectancy but CI crosses zero — PROMISING BUT INCONCLUSIVE")
        primary_result = "INCONCLUSIVE_POSITIVE"
    elif exp_net > 0:
        print(f"  RESULT: Barely positive expectancy, majority of resamples negative — WEAK")
        primary_result = "WEAK"
    else:
        print(f"  RESULT: Expectancy is zero or negative — NO CONFIRMATION")
        primary_result = "NO_CONFIRM"

    # ══════════════════════════════════════════════════════════
    #  SECTION 3: SECONDARY HYPOTHESIS — EUR vs non-EUR
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 3: SECONDARY HYPOTHESIS — EUR vs non-EUR")
    print(W)

    if eur_trades:
        rs_eur = [t['net_r'] for t in eur_trades]
        s_eur = stats(rs_eur)
        print(f"\n  EUR pairs ({s_eur['n']} trades):")
        print_stats("After costs", s_eur)
    else:
        s_eur = stats([])
        print(f"\n  EUR pairs: no trades in this dataset")

    if non_eur_trades:
        rs_non = [t['net_r'] for t in non_eur_trades]
        s_non = stats(rs_non)
        print(f"\n  Non-EUR pairs ({s_non['n']} trades):")
        print_stats("After costs", s_non)
    else:
        s_non = stats([])
        print(f"\n  Non-EUR pairs: no trades in this dataset")

    if eur_trades and non_eur_trades:
        diff = s_eur['exp'] - s_non['exp']
        print(f"\n  EUR - non-EUR expectancy difference: {diff:+.4f} R/trade")
        if diff > 0:
            print(f"  Direction: EUR outperforms (consistent with prior hypothesis)")
        else:
            print(f"  Direction: Non-EUR outperforms (against prior hypothesis)")
    elif not eur_trades:
        print(f"\n  NOTE: No EUR trades in this Holdout #2 batch.")
        print(f"  Cannot test EUR vs non-EUR hypothesis without EUR data.")
        print(f"  This dataset contains only non-EUR (AUD) pairs.")

    # ══════════════════════════════════════════════════════════
    #  SECTION 4: MONTE CARLO — Equity Distribution
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 4: BLOCK BOOTSTRAP MONTE CARLO — Equity Distribution")
    print(f"  ({N_SIMS} resampled sequences, block size 5, after realistic costs)")
    print(W)

    mc_final = []
    mc_dd = []
    mc_prof = 0

    for _ in range(N_SIMS):
        seq = []
        while len(seq) < n_trades:
            start = random.randint(0, n_trades - 1)
            for j in range(5):
                if len(seq) >= n_trades:
                    break
                seq.append(rs_net[(start + j) % n_trades])
        eq = 0; pk = 0; dd = 0
        for r in seq:
            eq += r; pk = max(pk, eq); dd = max(dd, pk - eq)
        mc_final.append(eq)
        mc_dd.append(dd)
        if eq > 0:
            mc_prof += 1

    mc_final.sort()
    mc_dd.sort()

    print(f"\n  Input: {n_trades} trades (after realistic costs)")
    print(f"  Observed total R: {s_net['R']:+.1f}")

    print(f"\n  Resampled Terminal Equity Distribution:")
    print(f"    {'Worst simulation':>22}: R = {mc_final[0]:>+6.1f}")
    for pct_label, idx in [("1st %ile", int(N_SIMS * 0.01)),
                            ("5th %ile", int(N_SIMS * 0.05)),
                            ("25th %ile", int(N_SIMS * 0.25)),
                            ("Median", int(N_SIMS * 0.50)),
                            ("75th %ile", int(N_SIMS * 0.75)),
                            ("95th %ile", int(N_SIMS * 0.95))]:
        print(f"    {pct_label:>22}: R = {mc_final[idx]:>+6.1f}")

    print(f"\n  Max Drawdown Distribution:")
    for pct_label, idx in [("Median DD", int(N_SIMS * 0.50)),
                            ("75th %ile DD", int(N_SIMS * 0.75)),
                            ("95th %ile DD", int(N_SIMS * 0.95)),
                            ("99th %ile DD", int(N_SIMS * 0.99))]:
        print(f"    {pct_label:>22}: {mc_dd[idx]:.1f}R")

    print(f"\n  P(profitable):  {mc_prof / N_SIMS * 100:.1f}%")
    p_loss_5r = sum(1 for e in mc_final if e < -5) / N_SIMS * 100
    print(f"  P(lose > 5R):   {p_loss_5r:.1f}%")

    # ══════════════════════════════════════════════════════════
    #  SECTION 5: TEMPORAL BREAKDOWN
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 5: TEMPORAL BREAKDOWN")
    print(W)

    quarters = OrderedDict()
    for t in v2:
        q = f"{t['entry_dt'].year} Q{(t['entry_dt'].month - 1) // 3 + 1}"
        quarters.setdefault(q, []).append(t)

    print(f"\n  {'Quarter':>12}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R(net)':>7}  {'Exp':>7}")
    print(f"  {'─'*12}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}")
    for q, trades in quarters.items():
        rs_q = [t['net_r'] for t in trades]
        s_q = stats(rs_q)
        flag = " <<<" if s_q['exp'] < -0.1 else ""
        print(f"  {q:>12}  {s_q['n']:>4}  {s_q['wr']:>5.1f}%  {s_q['pf']:>5.2f}  "
              f"{s_q['R']:>+6.1f}  {s_q['exp']:>+6.3f}{flag}")

    # Pair x Quarter
    print(f"\n  ── Pair x Quarter Breakdown (net R) ──")
    all_quarters_sorted = list(quarters.keys())
    header = f"  {'Pair':>10}"
    for q in all_quarters_sorted:
        header += f"  {q:>10}"
    header += f"  {'Total':>8}"
    print(header)
    print(f"  {'─'*10}" + f"  {'─'*10}" * len(all_quarters_sorted) + f"  {'─'*8}")
    pair_q = defaultdict(lambda: defaultdict(list))
    for t in v2:
        q = f"{t['entry_dt'].year} Q{(t['entry_dt'].month - 1) // 3 + 1}"
        pair_q[t['pair']][q].append(t['net_r'])
    for pair in pairs:
        row = f"  {pair:>10}"
        pair_total = 0
        for q in all_quarters_sorted:
            rs_pq = pair_q[pair][q]
            if rs_pq:
                r_sum = sum(rs_pq)
                pair_total += r_sum
                cell = f"{r_sum:+.1f}({len(rs_pq)})"
                row += f"  {cell:>10}"
            else:
                row += f"  {'--':>10}"
        row += f"  {pair_total:>+7.1f}"
        print(row)

    # Concentration check
    pair_contribs = {}
    for pair in pairs:
        pair_contribs[pair] = sum(t['net_r'] for t in v2 if t['pair'] == pair)
    total_r = s_net['R']
    if total_r != 0:
        print(f"\n  Profit concentration:")
        for pair in sorted(pair_contribs, key=lambda p: pair_contribs[p], reverse=True):
            pct = pair_contribs[pair] / abs(total_r) * 100
            print(f"    {pair:>10}: {pair_contribs[pair]:+.1f}R ({pct:+.0f}% of total)")

    # ══════════════════════════════════════════════════════════
    #  SECTION 6: TRADE-BY-TRADE LOG
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 6: TRADE-BY-TRADE LOG")
    print(W)

    print(f"\n  {'#':>3}  {'Pair':>8}  {'Entry Date':>18}  {'Entry':>8}  {'Stop':>7}  "
          f"{'Gross R':>8}  {'Cost R':>7}  {'Net R':>7}  {'Exit':>5}  {'Bars':>4}")
    print(f"  {'─'*3}  {'─'*8}  {'─'*18}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*4}")
    for i, t in enumerate(v2):
        _, bars, reason = sim_stale(t)
        print(f"  {i+1:>3}  {t['pair']:>8}  {t['entry_dt'].strftime('%Y-%m-%d %H:%M'):>18}  "
              f"{t['ep']:.5f}  {t['stop_pips']:>6.1f}p  "
              f"{t['final_r']:>+7.3f}  {t['cost_r']:>6.4f}  {t['net_r']:>+6.3f}  "
              f"{reason:>5}  {bars:>4}")

    # ══════════════════════════════════════════════════════════
    #  SECTION 7: COMPARISON WITH PRIOR OOS
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 7: COMPARISON WITH PRIOR RESULTS")
    print(f"  (For context only — Holdout #2 standalone result above is the TEST)")
    print(W)

    prior_exp = 0.031
    prior_ci = (-0.091, +0.154)
    prior_n = 109
    print(f"\n  Prior OOS: {prior_n} trades, Exp={prior_exp:+.3f}, 90% CI [{prior_ci[0]:+.3f}, {prior_ci[1]:+.3f}]")
    print(f"  Holdout #2: {n_trades} trades, Exp={exp_net:+.4f}, Block-5 90% CI [{lo_5:+.4f}, {hi_5:+.4f}]")

    if exp_net > 0 and prior_exp > 0:
        print(f"\n  Both positive — direction consistent")
    elif exp_net <= 0 and prior_exp > 0:
        print(f"\n  Prior positive, Holdout #2 zero/negative — inconsistent")

    # ══════════════════════════════════════════════════════════
    #  SECTION 8: FINAL VERDICT
    # ══════════════════════════════════════════════════════════
    print(f"\n{W}")
    print("  SECTION 8: FINAL VERDICT — HOLDOUT #2")
    print(W)

    print(f"""
  ┌───────────────────────────────────────────────────────────────────┐
  │             HOLDOUT #2 PREREGISTERED RESULTS                     │
  │                  All figures AFTER realistic costs                │
  ├──────────────────────────┬───────────────────────────────────────┤
  │  Trade Count             │  {n_trades:>8}                             │
  │  Win Rate                │  {s_net['wr']:>7.1f}%                            │
  │  Profit Factor           │  {s_net['pf']:>8.2f}                           │
  │  Expectancy (R/trade)    │  {s_net['exp']:>+8.4f}                           │
  │  Total R                 │  {s_net['R']:>+8.1f}                           │
  │  Max Drawdown (R)        │  {s_net['mdd']:>8.1f}                           │
  │  R / Max DD              │  {s_net['rdd']:>8.2f}                           │
  ├──────────────────────────┼───────────────────────────────────────┤
  │  Block-5 Bootstrap 90% CI│  [{lo_5:+.4f}, {hi_5:+.4f}]               │
  │  Cluster Bootstrap 90% CI│  [{c_lo:+.4f}, {c_hi:+.4f}]               │
  │  Block resamples > 0     │  {ppos_5:>7.1f}%                            │
  │  Cluster resamples > 0   │  {c_ppos:>7.1f}%                            │
  ├──────────────────────────┼───────────────────────────────────────┤
  │  MC P(profitable)        │  {mc_prof / N_SIMS * 100:>7.1f}%                            │
  │  MC Median terminal R    │  {mc_final[N_SIMS // 2]:>+8.1f}                           │
  │  MC 95th %ile DD         │  {mc_dd[int(N_SIMS * 0.95)]:.1f}R                              │
  ├──────────────────────────┼───────────────────────────────────────┤
  │  Pessimistic cost Exp    │  {s_pess['exp']:>+8.4f}                           │
  │  Pessimistic cost Total  │  {s_pess['R']:>+8.1f}                           │
  └──────────────────────────┴───────────────────────────────────────┘
""")

    checks = []
    checks_passed = 0

    if s_net['exp'] > 0:
        checks_passed += 1
        checks.append(f"  [PASS] After-cost expectancy positive ({s_net['exp']:+.4f})")
    else:
        checks.append(f"  [FAIL] After-cost expectancy not positive ({s_net['exp']:+.4f})")

    if s_net['pf'] > 1.0:
        checks_passed += 1
        checks.append(f"  [PASS] Profit factor > 1.0 ({s_net['pf']:.2f})")
    else:
        checks.append(f"  [FAIL] Profit factor <= 1.0 ({s_net['pf']:.2f})")

    if s_pess['exp'] > 0:
        checks_passed += 1
        checks.append(f"  [PASS] Positive under pessimistic costs ({s_pess['exp']:+.4f})")
    else:
        checks.append(f"  [FAIL] Not positive under pessimistic costs ({s_pess['exp']:+.4f})")

    max_pair_pct = max(abs(pair_contribs[p]) / abs(total_r) * 100 for p in pairs) if total_r != 0 else 100
    if max_pair_pct < 60:
        checks_passed += 1
        checks.append(f"  [PASS] No catastrophic concentration (max pair: {max_pair_pct:.0f}%)")
    else:
        checks.append(f"  [WARN] Concentration risk (max pair: {max_pair_pct:.0f}%)")

    if lo_5 > 0:
        checks_passed += 1
        checks.append(f"  [PASS] Block bootstrap 90% CI entirely positive")
    else:
        checks.append(f"  [    ] Block bootstrap CI crosses zero")

    if c_lo > 0:
        checks_passed += 1
        checks.append(f"  [PASS] Cluster bootstrap 90% CI entirely positive")
    else:
        checks.append(f"  [    ] Cluster bootstrap CI crosses zero")

    print(f"  Evidence checklist ({checks_passed}/6):")
    for c in checks:
        print(c)

    print()
    if primary_result == "STRONG_CONFIRM":
        print(f"  ╔═══════════════════════════════════════════════════════════════════╗")
        print(f"  ║  CLASSIFICATION: STRONG CONFIRMATION                            ║")
        print(f"  ║  Both CIs positive — edge confirmed on independent data         ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════╝")
    elif primary_result == "MODERATE_CONFIRM":
        print(f"  ╔═══════════════════════════════════════════════════════════════════╗")
        print(f"  ║  CLASSIFICATION: MODERATE CONFIRMATION                          ║")
        print(f"  ║  Expectancy positive, at least one CI excludes zero             ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════╝")
    elif primary_result == "INCONCLUSIVE_POSITIVE":
        print(f"  ╔═══════════════════════════════════════════════════════════════════╗")
        print(f"  ║  CLASSIFICATION: PROMISING BUT INCONCLUSIVE                     ║")
        print(f"  ║  Positive expectancy but CI includes zero — cannot rule out     ║")
        print(f"  ║  noise at this sample size. Per protocol: keep V3 frozen,       ║")
        print(f"  ║  continue data collection, do NOT modify parameters.            ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════╝")
    elif primary_result == "WEAK":
        print(f"  ╔═══════════════════════════════════════════════════════════════════╗")
        print(f"  ║  CLASSIFICATION: WEAK EVIDENCE                                  ║")
        print(f"  ║  Barely positive, most resamples negative — not confirmed       ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════╝")
    else:
        print(f"  ╔═══════════════════════════════════════════════════════════════════╗")
        print(f"  ║  CLASSIFICATION: NO CONFIRMATION                                ║")
        print(f"  ║  After-cost expectancy is zero or negative on holdout data      ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════╝")

    if n_trades < 300:
        print(f"\n  !! IMPORTANT: Only {n_trades} trades — below 300 minimum per stopping rule.")
        print(f"  !! Per protocol: extend by 6 calendar months and export more pairs.")
        print(f"  !! This is a PARTIAL result. Additional data needed for conclusion.")
    elif n_trades < 100:
        print(f"\n  !! CRITICAL: Only {n_trades} trades — sample far too small for any conclusion.")

    if not eur_trades:
        print(f"\n  NOTE: This batch contains only non-EUR (AUD) pairs.")
        print(f"  The EUR vs non-EUR hypothesis cannot be tested yet.")
        print(f"  EUR pair data still needed to complete Holdout #2.")

    print(f"\n  DO NOT modify V3 parameters based on these results.")
    print(f"  The strategy is FROZEN until the full Holdout #2 is complete.")

    print(f"\n{W}")
    print("  HOLDOUT #2 ANALYSIS COMPLETE")
    print(W)
