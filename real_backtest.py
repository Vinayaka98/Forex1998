#!/usr/bin/env python3
"""
Backtest Forex1998 Blueprint V3 Pro using REAL broker data (BlackBull 4H).
Reads TradingView-exported CSVs that contain the indicator's Active SL/TP columns.
"""
import csv, os, sys
from datetime import datetime

DATA_DIR = "/root/.claude/uploads/c9dd1cc3-70c3-5800-b09b-3644f5933104"

FILES = {
    "USDCAD": "1fb1e7cb-BLACKBULL_USDCAD_240.csv",
    "USDJPY": "e53fd9ee-BLACKBULL_USDJPY_240.csv",
    "NZDUSD": "51a3ea58-BLACKBULL_NZDUSD_240.csv",
    "AUDUSD": "f91b48c9-BLACKBULL_AUDUSD_240.csv",
    "EURUSD": "3436718b-BLACKBULL_EURUSD_240.csv",
}

def parse_float(s):
    s = s.strip()
    return float(s) if s else None

def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))

def extract_trades(rows):
    """Extract all trade periods from the exported data.
    Each contiguous sequence of bars with Active SL populated = one trade.
    """
    trades = []
    in_trade = False
    trade_bars = []

    for i, row in enumerate(rows):
        sl = parse_float(row['Active SL'])
        tp1 = parse_float(row['Active TP1'])
        tp2 = parse_float(row['Active TP2'])
        tp3 = parse_float(row['Active TP3'])
        o = float(row['open'])
        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])
        t = int(row['time'])

        bar_data = {
            'idx': i, 'time': t,
            'open': o, 'high': h, 'low': l, 'close': c,
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'bull_div': int(row['Bull Divergence']),
            'bear_div': int(row['Bear Div Warning']),
        }

        if sl is not None and not in_trade:
            in_trade = True
            trade_bars = [bar_data]
        elif sl is not None and in_trade:
            trade_bars.append(bar_data)
        elif sl is None and in_trade:
            in_trade = False
            trades.append(finalize_trade(trade_bars, rows, i))
            trade_bars = []

    if in_trade and trade_bars:
        trades.append(finalize_trade(trade_bars, rows, len(rows), still_open=True))

    return trades

def finalize_trade(trade_bars, all_rows, exit_bar_idx, still_open=False):
    """Compute trade outcome from the bar data."""
    first = trade_bars[0]
    last = trade_bars[-1]

    entry_bar_idx = first['idx']
    is_carryover = (entry_bar_idx == 0)

    # Derive entry price and stopDist
    # entry = (SL + TP1) / 2 from first bar (works for both carryover and new trades)
    # For non-carryover: entry should equal first bar's close
    sl0 = first['sl']
    tp1_0 = first['tp1']
    tp2_0 = first['tp2']

    if sl0 is not None and tp1_0 is not None:
        entry_price = (sl0 + tp1_0) / 2.0
        stop_dist = tp1_0 - entry_price  # 1R
    else:
        entry_price = first['close']
        stop_dist = abs(first['close'] - sl0) if sl0 else 0.001

    # Validate for non-carryover trades
    if not is_carryover and tp1_0 is not None:
        expected_entry = first['close']
        entry_diff = abs(entry_price - expected_entry)
        if stop_dist > 0 and entry_diff / stop_dist > 0.1:
            # Use close as entry for non-carryover
            entry_price = expected_entry
            stop_dist = abs(entry_price - sl0) if sl0 else stop_dist

    # Track trade bars for max favorable/adverse excursion
    max_high = max(b['high'] for b in trade_bars)
    min_low = min(b['low'] for b in trade_bars)

    # Determine exit
    if still_open:
        exit_price = last['close']
        exit_type = "STILL_OPEN"
    else:
        # Exit bar is all_rows[exit_bar_idx]
        exit_bar = all_rows[exit_bar_idx] if exit_bar_idx < len(all_rows) else None
        last_sl = last['sl']
        last_tp2 = last['tp2']  # This is activeTP (buyTarget)

        if exit_bar:
            exit_h = float(exit_bar['high'])
            exit_l = float(exit_bar['low'])
            exit_c = float(exit_bar['close'])

            # Pine Script exit priority: SL first, then TP, then time
            # On the exit bar, the script checks:
            # 1. Trail update (may raise SL)
            # 2. low <= activeSL → exit at SL
            # 3. high >= activeTP → exit at TP
            # 4. timeExit → exit at close

            if last_sl is not None and exit_l <= last_sl:
                exit_price = last_sl
                exit_type = "SL_HIT"
            elif last_tp2 is not None and exit_h >= last_tp2:
                exit_price = last_tp2
                exit_type = "TP_HIT"
            else:
                exit_price = exit_c
                exit_type = "TIME_EXIT"
        else:
            exit_price = last['close']
            exit_type = "DATA_END"

    pnl = exit_price - entry_price
    r_multiple = pnl / stop_dist if stop_dist > 0 else 0.0
    bars_held = len(trade_bars)

    # Check if TP1 was reached during trade
    tp1_reached = max_high >= tp1_0 if tp1_0 else False
    tp2_reached = max_high >= tp2_0 if tp2_0 else False

    return {
        'entry_bar': entry_bar_idx,
        'exit_bar': exit_bar_idx,
        'bars_held': bars_held,
        'is_carryover': is_carryover,
        'entry_price': entry_price,
        'stop_dist': stop_dist,
        'initial_sl': sl0,
        'final_sl': last['sl'],
        'tp1': tp1_0,
        'tp2': tp2_0,
        'exit_price': exit_price,
        'exit_type': exit_type,
        'pnl': pnl,
        'r_multiple': r_multiple,
        'tp1_reached': tp1_reached,
        'tp2_reached': tp2_reached,
        'max_high': max_high,
        'min_low': min_low,
        'entry_time': first['time'],
        'still_open': still_open,
    }

def format_time(ts):
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

def run_backtest():
    all_trades = {}
    grand_trades = []

    print("=" * 90)
    print("  FOREX1998 BLUEPRINT V3 PRO — REAL DATA BACKTEST")
    print("  Data: BlackBull Markets, 4H Timeframe")
    print("=" * 90)
    print()

    for pair, fname in FILES.items():
        path = os.path.join(DATA_DIR, fname)
        rows = load_csv(path)
        trades = extract_trades(rows)
        all_trades[pair] = trades

        # Date range
        t0 = int(rows[0]['time'])
        t1 = int(rows[-1]['time'])

        print(f"{'─' * 90}")
        print(f"  {pair}  |  {len(rows)} bars  |  {format_time(t0)} → {format_time(t1)}")
        print(f"{'─' * 90}")

        if not trades:
            print("  No trades found.\n")
            continue

        wins = 0
        losses = 0
        be = 0
        total_r = 0.0
        gross_win_r = 0.0
        gross_loss_r = 0.0

        for i, t in enumerate(trades):
            tag = ""
            if t['is_carryover']:
                tag = " [CARRYOVER]"
            if t['still_open']:
                tag = " [STILL OPEN]"

            if t['r_multiple'] > 0.05:
                wins += 1
                gross_win_r += t['r_multiple']
                result = "WIN"
            elif t['r_multiple'] < -0.05:
                losses += 1
                gross_loss_r += abs(t['r_multiple'])
                result = "LOSS"
            else:
                be += 1
                result = "BE"

            total_r += t['r_multiple']

            tp1_flag = "✓" if t['tp1_reached'] else "✗"
            print(f"  #{i+1:2d}  {format_time(t['entry_time'])}  "
                  f"Entry={t['entry_price']:.5f}  "
                  f"Exit={t['exit_price']:.5f}  "
                  f"{t['exit_type']:10s}  "
                  f"R={t['r_multiple']:+.2f}  "
                  f"TP1={tp1_flag}  "
                  f"{t['bars_held']:2d}b  "
                  f"{result}{tag}")

        total = wins + losses + be
        wr = wins / total * 100 if total > 0 else 0
        pf = gross_win_r / gross_loss_r if gross_loss_r > 0 else float('inf')
        avg_r = total_r / total if total > 0 else 0
        avg_win = gross_win_r / wins if wins > 0 else 0
        avg_loss = gross_loss_r / losses if losses > 0 else 0

        print(f"\n  {pair} Summary: {total} trades  |  "
              f"W:{wins} L:{losses} BE:{be}  |  "
              f"WR: {wr:.1f}%  |  "
              f"PF: {pf:.2f}  |  "
              f"Total R: {total_r:+.2f}")
        print(f"  Avg R/trade: {avg_r:+.3f}  |  "
              f"Avg Win: +{avg_win:.2f}R  |  "
              f"Avg Loss: -{avg_loss:.2f}R")
        print()

        grand_trades.extend(trades)

    # Combined results
    print("=" * 90)
    print("  COMBINED RESULTS — ALL 5 PAIRS")
    print("=" * 90)

    total = len(grand_trades)
    wins = sum(1 for t in grand_trades if t['r_multiple'] > 0.05)
    losses = sum(1 for t in grand_trades if t['r_multiple'] < -0.05)
    be = total - wins - losses

    carryover = sum(1 for t in grand_trades if t['is_carryover'])
    still_open = sum(1 for t in grand_trades if t['still_open'])

    total_r = sum(t['r_multiple'] for t in grand_trades)
    gross_win_r = sum(t['r_multiple'] for t in grand_trades if t['r_multiple'] > 0.05)
    gross_loss_r = sum(abs(t['r_multiple']) for t in grand_trades if t['r_multiple'] < -0.05)

    wr = wins / total * 100 if total > 0 else 0
    pf = gross_win_r / gross_loss_r if gross_loss_r > 0 else float('inf')
    avg_r = total_r / total if total > 0 else 0
    avg_win = gross_win_r / wins if wins > 0 else 0
    avg_loss = gross_loss_r / losses if losses > 0 else 0

    # Excluding carryover trades
    clean = [t for t in grand_trades if not t['is_carryover'] and not t['still_open']]
    clean_total = len(clean)
    clean_wins = sum(1 for t in clean if t['r_multiple'] > 0.05)
    clean_losses = sum(1 for t in clean if t['r_multiple'] < -0.05)
    clean_be = clean_total - clean_wins - clean_losses
    clean_total_r = sum(t['r_multiple'] for t in clean)
    clean_gross_win = sum(t['r_multiple'] for t in clean if t['r_multiple'] > 0.05)
    clean_gross_loss = sum(abs(t['r_multiple']) for t in clean if t['r_multiple'] < -0.05)
    clean_wr = clean_wins / clean_total * 100 if clean_total > 0 else 0
    clean_pf = clean_gross_win / clean_gross_loss if clean_gross_loss > 0 else float('inf')
    clean_avg_r = clean_total_r / clean_total if clean_total > 0 else 0
    clean_avg_win = clean_gross_win / clean_wins if clean_wins > 0 else 0
    clean_avg_loss = clean_gross_loss / clean_losses if clean_losses > 0 else 0

    # Exit type distribution
    exit_types = {}
    for t in grand_trades:
        et = t['exit_type']
        exit_types[et] = exit_types.get(et, 0) + 1

    # TP1 reach rate
    tp1_reached = sum(1 for t in grand_trades if t['tp1_reached'])
    tp2_reached = sum(1 for t in grand_trades if t['tp2_reached'])

    # Bars held distribution
    bars_list = [t['bars_held'] for t in grand_trades]
    avg_bars = sum(bars_list) / len(bars_list) if bars_list else 0
    max_bars = max(bars_list) if bars_list else 0

    print(f"\n  ALL TRADES (including carryover):")
    print(f"  {'─' * 50}")
    print(f"  Total Trades:     {total}")
    print(f"    Carryover:      {carryover} (pre-existing when data starts)")
    print(f"    Still Open:     {still_open}")
    print(f"  Wins:             {wins}")
    print(f"  Losses:           {losses}")
    print(f"  Breakeven:        {be}")
    print(f"  Win Rate:         {wr:.1f}%")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"  Total R:          {total_r:+.2f}R")
    print(f"  Avg R/Trade:      {avg_r:+.3f}R")
    print(f"  Avg Win:          +{avg_win:.2f}R")
    print(f"  Avg Loss:         -{avg_loss:.2f}R")

    print(f"\n  CLEAN TRADES (excluding carryover & open):")
    print(f"  {'─' * 50}")
    print(f"  Total Trades:     {clean_total}")
    print(f"  Wins:             {clean_wins}")
    print(f"  Losses:           {clean_losses}")
    print(f"  Breakeven:        {clean_be}")
    print(f"  Win Rate:         {clean_wr:.1f}%")
    print(f"  Profit Factor:    {clean_pf:.2f}")
    print(f"  Total R:          {clean_total_r:+.2f}R")
    print(f"  Avg R/Trade:      {clean_avg_r:+.3f}R")
    print(f"  Avg Win:          +{clean_avg_win:.2f}R")
    print(f"  Avg Loss:         -{clean_avg_loss:.2f}R")

    print(f"\n  EXIT TYPE DISTRIBUTION:")
    print(f"  {'─' * 50}")
    for et, count in sorted(exit_types.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"    {et:15s}  {count:3d}  ({pct:.1f}%)")

    print(f"\n  TARGET REACH RATES:")
    print(f"  {'─' * 50}")
    print(f"    TP1 (1R) reached:  {tp1_reached}/{total} ({tp1_reached/total*100:.1f}%)")
    print(f"    TP2 (2R) reached:  {tp2_reached}/{total} ({tp2_reached/total*100:.1f}%)")

    print(f"\n  BARS HELD:")
    print(f"  {'─' * 50}")
    print(f"    Average:    {avg_bars:.1f} bars ({avg_bars*4:.0f} hours)")
    print(f"    Maximum:    {max_bars} bars ({max_bars*4:.0f} hours)")

    # Per-pair summary table
    print(f"\n  PER-PAIR BREAKDOWN:")
    print(f"  {'─' * 80}")
    print(f"  {'Pair':8s} {'Trades':>7s} {'Wins':>5s} {'Loss':>5s} {'BE':>4s} {'WR%':>6s} {'PF':>6s} {'TotalR':>8s} {'AvgR':>7s}")
    print(f"  {'─' * 80}")

    for pair in FILES:
        pt = all_trades[pair]
        if not pt:
            continue
        pw = sum(1 for t in pt if t['r_multiple'] > 0.05)
        pl = sum(1 for t in pt if t['r_multiple'] < -0.05)
        pb = len(pt) - pw - pl
        ptr = sum(t['r_multiple'] for t in pt)
        pgw = sum(t['r_multiple'] for t in pt if t['r_multiple'] > 0.05)
        pgl = sum(abs(t['r_multiple']) for t in pt if t['r_multiple'] < -0.05)
        pwr = pw / len(pt) * 100
        ppf = pgw / pgl if pgl > 0 else float('inf')
        pavg = ptr / len(pt)
        print(f"  {pair:8s} {len(pt):7d} {pw:5d} {pl:5d} {pb:4d} {pwr:5.1f}% {ppf:6.2f} {ptr:+7.2f}R {pavg:+6.3f}R")

    print(f"  {'─' * 80}")
    print(f"  {'TOTAL':8s} {total:7d} {wins:5d} {losses:5d} {be:4d} {wr:5.1f}% {pf:6.2f} {total_r:+7.2f}R {avg_r:+6.3f}R")
    print()

    # Win streak / loss streak
    results_seq = []
    for t in grand_trades:
        if t['r_multiple'] > 0.05:
            results_seq.append('W')
        elif t['r_multiple'] < -0.05:
            results_seq.append('L')
        else:
            results_seq.append('B')

    max_win_streak = 0
    max_loss_streak = 0
    cur_streak = 0
    cur_type = None
    for r in results_seq:
        if r == cur_type:
            cur_streak += 1
        else:
            cur_type = r
            cur_streak = 1
        if r == 'W':
            max_win_streak = max(max_win_streak, cur_streak)
        elif r == 'L':
            max_loss_streak = max(max_loss_streak, cur_streak)

    print(f"  STREAKS:")
    print(f"  {'─' * 50}")
    print(f"    Max Win Streak:   {max_win_streak}")
    print(f"    Max Loss Streak:  {max_loss_streak}")

    # Equity curve (cumulative R)
    print(f"\n  EQUITY CURVE (Cumulative R):")
    print(f"  {'─' * 50}")
    cum_r = 0.0
    max_r = 0.0
    max_dd = 0.0
    for i, t in enumerate(grand_trades):
        cum_r += t['r_multiple']
        max_r = max(max_r, cum_r)
        dd = max_r - cum_r
        max_dd = max(max_dd, dd)
        pair_name = ""
        for p, ts in all_trades.items():
            if t in ts:
                pair_name = p
                break
        if (i + 1) % 5 == 0 or i == 0 or i == len(grand_trades) - 1:
            print(f"    Trade {i+1:3d} ({pair_name:6s}):  CumR = {cum_r:+7.2f}R  |  DD = {dd:.2f}R")

    print(f"\n  Max Drawdown:  {max_dd:.2f}R")
    print()
    print("=" * 90)

if __name__ == "__main__":
    run_backtest()
