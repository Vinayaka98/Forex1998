#!/usr/bin/env python3
"""
New OOS Validation — Stale Exit on 5 fresh EUR pair CSVs (Jul-Sep 2026)
=======================================================================
Validates the stale exit (8 bars / <0.5R MFE) on completely unseen data.
These files have columns: Active SL, Active TP2, Active TP1, Active TP3,
Sell SL, Sell TP2, Sell TP1, Sell TP3, Wk POC/VAH/VAL, Mo POC/VAH/VAL,
Bull Divergence, Bear Div Warning
"""
import csv, os, math, argparse
from datetime import datetime, timezone

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

parser = argparse.ArgumentParser(description="New OOS Validation — 7 EUR pairs")
parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help="Directory containing CSV data files (default: ../data/)")
_args, _ = parser.parse_known_args()
UPLOAD_DIR = os.path.abspath(_args.data_dir)

NEW_OOS_FILES = {
    "EURUSD": "5b931546-OANDA_EURUSD_240_15da8.csv",
    "EURJPY": "1c474f00-OANDA_EURJPY_240_d1869.csv",
    "EURGBP": "2875719d-OANDA_EURGBP_240_13f27.csv",
    "EURAUD": "41cccecd-OANDA_EURAUD_240_cfbf8.csv",
    "EURCAD": "1f6729b9-OANDA_EURCAD_240_b8e32.csv",
    "EURNZD": "d1260ae5-OANDA_EURNZD_240_9279b.csv",
    "EURCHF": "44eaa2d3-OANDA_EURCHF_240_27717.csv",
}

# Also load prior dev & OOS for comparison
DEV_FILES = {
    "EURNZD": ("2c010574-OANDA_EURNZD_240.csv", "Active TP"),
    "EURCAD": ("52d23423-OANDA_EURCAD_240.csv", "Active TP"),
    "EURAUD": ("70ab8fef-OANDA_EURAUD_240.csv", "Active TP"),
    "EURGBP": ("d8d9759a-OANDA_EURGBP_240.csv", "Active TP"),
    "EURUSD": ("8505bf9d-OANDA_EURUSD_240.csv", "Active TP"),
}

PRIOR_OOS_FILES = {
    "EURCHF":    ("92b510fc-OANDA_EURCHF_240.csv", "Active TP"),
    "BB_EURUSD": ("3436718b-BLACKBULL_EURUSD_240.csv", "Active TP2"),
    "BB_USDCAD": ("1fb1e7cb-BLACKBULL_USDCAD_240.csv", "Active TP2"),
    "BB_NZDUSD": ("51a3ea58-BLACKBULL_NZDUSD_240.csv", "Active TP2"),
    "BB_AUDUSD": ("f91b48c9-BLACKBULL_AUDUSD_240.csv", "Active TP2"),
    "BB_USDJPY": ("e53fd9ee-BLACKBULL_USDJPY_240.csv", "Active TP2"),
}

def load_csv(fp, tp_col="Active TP2"):
    rows = []
    with open(fp) as f:
        for r in csv.DictReader(f):
            rows.append({
                'time': int(r['time']),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'sl': float(r['Active SL']) if r.get('Active SL','').strip() else None,
                'tp': float(r[tp_col]) if r.get(tp_col,'').strip() else None,
            })
    return rows

def compute_atr(rows, p=14):
    a = [0.0]*len(rows)
    for i in range(len(rows)):
        if i == 0: a[i] = rows[i]['high']-rows[i]['low']
        else:
            tr = max(rows[i]['high']-rows[i]['low'],
                     abs(rows[i]['high']-rows[i-1]['close']),
                     abs(rows[i]['low']-rows[i-1]['close']))
            a[i] = (a[i-1]*(min(i,p)-1)+tr)/min(i,p) if i < p else (a[i-1]*(p-1)+tr)/p
    return a

def compute_adx(rows, p=14):
    n = len(rows); adx=[0.0]*n; pdm=[0.0]*n; mdm=[0.0]*n; tr=[0.0]*n
    for i in range(1,n):
        u=rows[i]['high']-rows[i-1]['high']; d=rows[i-1]['low']-rows[i]['low']
        pdm[i]=u if u>d and u>0 else 0; mdm[i]=d if d>u and d>0 else 0
        tr[i]=max(rows[i]['high']-rows[i]['low'],abs(rows[i]['high']-rows[i-1]['close']),abs(rows[i]['low']-rows[i-1]['close']))
    st=[0.0]*n;sp=[0.0]*n;sm=[0.0]*n
    for i in range(1,min(p+1,n)): st[p]+=tr[i];sp[p]+=pdm[i];sm[p]+=mdm[i]
    for i in range(p+1,n): st[i]=st[i-1]-st[i-1]/p+tr[i];sp[i]=sp[i-1]-sp[i-1]/p+pdm[i];sm[i]=sm[i-1]-sm[i-1]/p+mdm[i]
    dx=[0.0]*n
    for i in range(p,n):
        if st[i]>0:
            pi_=100*sp[i]/st[i];mi_=100*sm[i]/st[i]
            if pi_+mi_>0: dx[i]=100*abs(pi_-mi_)/(pi_+mi_)
    for i in range(p*2,n):
        adx[i]=(sum(dx[p:p*2])/p) if i==p*2 else (adx[i-1]*(p-1)+dx[i])/p
    return adx

def percentrank(series, idx, length):
    if idx < length: return 50.0
    val = series[idx]
    count_below = sum(1 for j in range(idx - length, idx) if series[j] < val)
    return count_below / length * 100.0

def extract_trades(pair, fp, tp_col="Active TP2"):
    rows = load_csv(fp, tp_col)
    atr = compute_atr(rows)
    adx = compute_adx(rows)
    trades = []; in_trade = False; prev_sl = None
    entry_bar = ep = sd = itp = 0
    direction = ""; rmfe = rmae = 0.0
    current_sl = current_tp = 0.0
    bdata = []

    for i, bar in enumerate(rows):
        sl = bar['sl']; tp = bar['tp']
        is_new = sl is not None and prev_sl is None

        if in_trade:
            if sl is not None: current_sl = sl
            bn = i - entry_bar
            if direction == "BUY":
                bhr=(bar['high']-ep)/sd; blr=(bar['low']-ep)/sd; bcr=(bar['close']-ep)/sd
                rmfe=max(rmfe,bhr); rmae=max(rmae,-blr)
            else:
                bhr=(ep-bar['low'])/sd; blr=(ep-bar['high'])/sd; bcr=(ep-bar['close'])/sd
                rmfe=max(rmfe,bhr); rmae=max(rmae,-blr)
            bdata.append({'bar':bn,'high_r':bhr,'low_r':blr,'close_r':bcr})
            xp=None; xreason=""
            if direction=="BUY":
                if bar['low']<=current_sl: xp=current_sl; xreason="SL"
                elif current_tp>0 and bar['high']>=current_tp: xp=current_tp; xreason="TP"
                elif sl is None: xp=bar['close']; xreason="IND"
            else:
                if bar['high']>=current_sl: xp=current_sl; xreason="SL"
                elif current_tp>0 and bar['low']<=current_tp: xp=current_tp; xreason="TP"
                elif sl is None: xp=bar['close']; xreason="IND"
            if xp is not None:
                rr=(xp-ep)/sd if direction=="BUY" else (ep-xp)/sd
                if xreason=="SL" and rr<-1.0: rr=-1.0
                if xreason=="TP":
                    tpr=abs(itp-ep)/sd; rr=min(rr,tpr)
                edt=datetime.fromtimestamp(rows[entry_bar]['time'],tz=timezone.utc)
                trades.append({
                    'pair':pair,'dir':direction,
                    'entry_time':rows[entry_bar]['time'],'entry_dt':edt,
                    'entry_bar_idx': entry_bar,
                    'ep':ep,'sd':sd,'itp_r':abs(itp-ep)/sd if itp>0 and sd>0 else 0,
                    'atr':atr[entry_bar],'adx':adx[entry_bar],
                    'atr_pctrank': percentrank(atr, entry_bar, 100),
                    'bd':bdata[:],'orig_r':rr,'orig_bars':len(bdata),
                    'orig_reason':xreason,'orig_mfe':rmfe,'orig_mae':rmae,
                    'raw_signal_on': True,
                })
                in_trade=False

        if not in_trade and is_new:
            entry_bar=i; ep=bar['close']; isl=sl; itp=tp if tp else 0
            current_sl=sl; current_tp=itp
            sd=abs(ep-isl)
            if sd==0: sd=0.0001
            direction="BUY" if isl<ep else "SELL"
            rmfe=0.0; rmae=0.0; bdata=[]
            in_trade=True
        prev_sl=sl
    return trades, rows, atr, adx

def apply_v2_gates(trades, atr_thr=66, adx_thr=18.0):
    filtered = []
    for t in sorted(trades, key=lambda x: x['entry_time']):
        if t['pair'] == "EURAUD": continue
        if t['atr_pctrank'] > atr_thr and t['adx'] < adx_thr: continue
        filtered.append(t)
    return filtered

def sim_stale_exit(trade, stale_bars, stale_mfe_thr):
    bd = trade['bd']
    if not bd: return trade['orig_r'], trade['orig_bars'], trade['orig_reason']
    max_mfe = 0.0
    for b in bd:
        max_mfe = max(max_mfe, b['high_r'])
        if b['bar'] >= stale_bars and max_mfe < stale_mfe_thr:
            return b['close_r'], b['bar'], "STALE"
    return trade['orig_r'], trade['orig_bars'], trade['orig_reason']

def stats(results):
    if not results: return {'n':0,'R':0,'wr':0,'pf':0,'exp':0,'mdd':0,'rdd':0,'aw':0,'al':0,'wins':0,'losses':0}
    n=len(results); tr=sum(t['r'] for t in results)
    w=[t for t in results if t['r']>=0.1]; l=[t for t in results if t['r']<=-0.1]
    gw=sum(t['r'] for t in w); gl=abs(sum(t['r'] for t in l))
    pf=gw/gl if gl>0 else 99.9
    eq=0;pk=0;mdd=0
    for t in results:
        eq+=t['r']; pk=max(pk,eq); mdd=max(mdd,pk-eq)
    aw=gw/len(w) if w else 0; al=gl/len(l) if l else 0
    return {'n':n,'R':tr,'wr':len(w)/n*100,'pf':pf,'exp':tr/n,
            'mdd':mdd,'aw':aw,'al':al,'rdd':tr/mdd if mdd>0 else 0,
            'wins':len(w),'losses':len(l)}

def print_stats(label, s, indent=2):
    sp = ' ' * indent
    print(f"{sp}{label}: {s['n']} trades  WR {s['wr']:.1f}%  PF {s['pf']:.2f}  "
          f"R {s['R']:+.1f}  Exp {s['exp']:+.3f}  MaxDD {s['mdd']:.1f}  R/DD {s['rdd']:.2f}  "
          f"AvgW {s['aw']:.2f}  AvgL {s['al']:.2f}")

W = '=' * 100
D = '-' * 100

# ═══════════════════════════════════════════════════════════
# LOAD NEW OOS DATA
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  LOADING NEW OOS DATA (Jul-Sep 2026 — 7 EUR pairs)")
print(W)

new_oos_trades = []
for pair, fname in sorted(NEW_OOS_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    trades, rows, atr, adx = extract_trades(pair, fp, "Active TP2")
    buy_c = sum(1 for t in trades if t['dir'] == 'BUY')
    sell_c = sum(1 for t in trades if t['dir'] == 'SELL')
    print(f"  {pair}: {len(rows)} bars, {len(trades)} trades ({buy_c} BUY, {sell_c} SELL)")
    for t in trades:
        print(f"    {t['entry_dt'].strftime('%Y-%m-%d %H:%M')} {t['dir']:>4} "
              f"R={t['orig_r']:+.2f}  MFE={t['orig_mfe']:.2f}  Bars={t['orig_bars']}  "
              f"Exit={t['orig_reason']}  ATR%={t['atr_pctrank']:.0f}  ADX={t['adx']:.1f}")
    new_oos_trades.extend(trades)

new_oos_trades.sort(key=lambda t: t['entry_time'])
print(f"\n  Total new OOS: {len(new_oos_trades)} trades")

# Apply V2 gates
new_oos_v2 = apply_v2_gates(new_oos_trades)
rejected = len(new_oos_trades) - len(new_oos_v2)
print(f"  After V2 gates: {len(new_oos_v2)} trades ({rejected} rejected)")

# Show which trades were rejected and why
if rejected > 0:
    print(f"\n  Rejected trades:")
    for t in new_oos_trades:
        if t not in new_oos_v2:
            reason = "EURAUD exclusion" if t['pair'] == "EURAUD" else f"High ATR ({t['atr_pctrank']:.0f}) + Low ADX ({t['adx']:.1f})"
            print(f"    {t['pair']} {t['entry_dt'].strftime('%Y-%m-%d %H:%M')} {t['dir']:>4} "
                  f"R={t['orig_r']:+.2f} — {reason}")


# ═══════════════════════════════════════════════════════════
# SECTION 1: NEW OOS BASELINE
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 1: NEW OOS BASELINE (V2 filtered)")
print(W)

new_oos_base = [{'r': t['orig_r'], **t} for t in new_oos_v2]
nb = stats(new_oos_base)
print_stats("\n  Baseline", nb, 2)

# Per-pair breakdown
print(f"\n  Per-pair breakdown:")
print(f"  {'Pair':>8}  {'N':>4}  {'BUY':>4}  {'SELL':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'MDD':>5}  {'R/DD':>5}  {'AvgW':>5}  {'AvgL':>5}")
print(f"  {'─'*8}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}")
for pair in sorted(set(t['pair'] for t in new_oos_v2)):
    pt = [{'r': t['orig_r'], **t} for t in new_oos_v2 if t['pair'] == pair]
    ps = stats(pt)
    buys = sum(1 for t in pt if t['dir'] == 'BUY')
    sells = sum(1 for t in pt if t['dir'] == 'SELL')
    print(f"  {pair:>8}  {ps['n']:>4}  {buys:>4}  {sells:>4}  {ps['wr']:>5.1f}%  {ps['pf']:>5.2f}  "
          f"{ps['R']:>+6.1f}  {ps['mdd']:>5.1f}  {ps['rdd']:>5.2f}  {ps['aw']:>5.2f}  {ps['al']:>5.2f}")


# ═══════════════════════════════════════════════════════════
# SECTION 2: STALE EXIT SWEEP ON NEW OOS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 2: STALE EXIT SWEEP — New OOS Data")
print(W)

stale_bars_list = [5, 8, 10, 12, 15, 20]
stale_mfe_list = [0.3, 0.5, 0.7, 1.0]

print(f"\n  {'Bars':>5}  {'MFE<':>5}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'MaxDD':>6}  {'R/DD':>5}  "
      f"{'Stale':>5}  {'ΔR':>6}")
print(f"  {'─'*5}  {'─'*5}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*6}  {'─'*5}  "
      f"{'─'*5}  {'─'*6}")

print(f"  {'BASE':>5}  {'─':>5}  {nb['n']:>4}  {nb['wr']:>5.1f}%  {nb['pf']:>5.2f}  {nb['R']:>+6.1f}  "
      f"{nb['exp']:>+6.3f}  {nb['mdd']:>5.1f}  {nb['rdd']:>5.2f}  {'0':>5}  {'+0.0':>6}")

for sb in stale_bars_list:
    for sm in stale_mfe_list:
        results = []
        stale_count = 0
        for t in new_oos_v2:
            r, bars, reason = sim_stale_exit(t, sb, sm)
            results.append({'r': r, **t, 'sim_reason': reason, 'sim_bars': bars})
            if reason == "STALE": stale_count += 1
        s = stats(results)
        delta_r = s['R'] - nb['R']
        marker = " *" if sb == 8 and sm == 0.5 else ""
        print(f"  {sb:>5}  {sm:>4.1f}R  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  "
              f"{s['exp']:>+6.3f}  {s['mdd']:>5.1f}  {s['rdd']:>5.2f}  {stale_count:>5}  {delta_r:>+5.1f}{marker}")


# ═══════════════════════════════════════════════════════════
# SECTION 3: TRADE-BY-TRADE for S=8/0.5R (our candidate)
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 3: TRADE-BY-TRADE — Stale S=8bars/<0.5R MFE on New OOS")
print(W)

changes = []
for t in new_oos_v2:
    r, bars, reason = sim_stale_exit(t, 8, 0.5)
    changes.append({
        'pair': t['pair'], 'dir': t['dir'],
        'date': t['entry_dt'].strftime('%Y-%m-%d %H:%M'),
        'orig_r': t['orig_r'], 'new_r': r, 'delta': r - t['orig_r'],
        'orig_bars': t['orig_bars'], 'new_bars': bars,
        'orig_reason': t['orig_reason'], 'new_reason': reason,
        'mfe': t['orig_mfe']
    })

stale_trades = [c for c in changes if c['new_reason'] == 'STALE']
helped = sum(1 for c in stale_trades if c['delta'] > 0.05)
hurt = sum(1 for c in stale_trades if c['delta'] < -0.05)
r_saved = sum(c['delta'] for c in stale_trades)

print(f"\n  {len(stale_trades)} trades hit stale exit: {helped} helped, {hurt} hurt, net {r_saved:+.2f}R")

if stale_trades:
    print(f"\n  {'#':>4}  {'Pair':>8}  {'Dir':>4}  {'Date':>18}  {'MFE':>5}  {'Orig R':>7}  {'New R':>7}  {'ΔR':>6}  "
          f"{'O.Bars':>6}  {'N.Bars':>6}  {'O.Exit':>6}")
    print(f"  {'─'*4}  {'─'*8}  {'─'*4}  {'─'*18}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*6}  "
          f"{'─'*6}  {'─'*6}  {'─'*6}")
    for i, c in enumerate(sorted(stale_trades, key=lambda x: x['delta'], reverse=True)):
        marker = " +" if c['delta'] > 0.05 else " -" if c['delta'] < -0.05 else "  "
        print(f"  {i+1:>4}  {c['pair']:>8}  {c['dir']:>4}  {c['date']:>18}  {c['mfe']:>5.2f}  {c['orig_r']:>+6.2f}  "
              f"{c['new_r']:>+6.2f}  {c['delta']:>+5.2f}  {c['orig_bars']:>6}  {c['new_bars']:>6}  "
              f"{c['orig_reason']:>6}{marker}")


# ═══════════════════════════════════════════════════════════
# SECTION 4: FULL COMPARISON TABLE — Dev + Prior OOS + New OOS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 4: FULL COMPARISON — Dev / Prior OOS / New OOS")
print(W)

# Load dev trades
print("\n  Loading dev trades for comparison...")
dev_trades = []
for pair, (fname, tp_col) in sorted(DEV_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades, _, _, _ = extract_trades(pair, fp, tp_col)
        dev_trades.extend(trades)
dev_trades.sort(key=lambda t: t['entry_time'])
dev_v2 = apply_v2_gates(dev_trades)
print(f"  Dev: {len(dev_v2)} V2 trades")

# Load prior OOS trades
prior_oos_trades = []
for pair, (fname, tp_col) in sorted(PRIOR_OOS_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades, _, _, _ = extract_trades(pair, fp, tp_col)
        prior_oos_trades.extend(trades)
prior_oos_trades.sort(key=lambda t: t['entry_time'])
prior_oos_v2 = apply_v2_gates(prior_oos_trades)
print(f"  Prior OOS: {len(prior_oos_v2)} V2 trades")
print(f"  New OOS: {len(new_oos_v2)} V2 trades")

# Build comparison
datasets = [
    ("Dev", dev_v2),
    ("Prior OOS", prior_oos_v2),
    ("New OOS", new_oos_v2),
    ("All OOS", prior_oos_v2 + new_oos_v2),
]

stale_configs = [
    ("V2 baseline", None, None),
    ("Stale S=8/0.5R", 8, 0.5),
    ("Stale S=8/0.3R", 8, 0.3),
    ("Stale S=10/0.5R", 10, 0.5),
    ("Stale S=12/0.5R", 12, 0.5),
    ("Stale S=5/0.5R", 5, 0.5),
]

print(f"\n  {'Strategy':>22}  ", end="")
for dname, _ in datasets:
    print(f"{'R':>6}  {'PF':>5}  {'DD':>5}  {'R/DD':>5}  {'N':>3}  |", end="")
print()
print(f"  {'─'*22}  ", end="")
for _ in datasets:
    print(f"{'─'*6}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*3}  |", end="")
print()

for sname, sb, sm in stale_configs:
    print(f"  {sname:>22}  ", end="")
    for dname, dv2 in datasets:
        if sb is None:
            results = [{'r': t['orig_r']} for t in dv2]
        else:
            results = []
            for t in dv2:
                r, _, reason = sim_stale_exit(t, sb, sm)
                results.append({'r': r})
        s = stats(results)
        print(f"{s['R']:>+5.1f}  {s['pf']:>5.2f}  {s['mdd']:>5.1f}  {s['rdd']:>5.2f}  {s['n']:>3}  |", end="")
    print()


# ═══════════════════════════════════════════════════════════
# SECTION 5: EQUITY CURVE DETAILS for S=8/0.5R
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 5: EQUITY CURVE — S=8/0.5R on New OOS (trade by trade)")
print(W)

equity = 0.0
peak = 0.0
dd = 0.0
print(f"\n  {'#':>4}  {'Pair':>8}  {'Dir':>4}  {'Date':>18}  {'R':>7}  {'Equity':>7}  {'DD':>5}  {'Exit':>6}  {'MFE':>5}  {'Bars':>4}")
print(f"  {'─'*4}  {'─'*8}  {'─'*4}  {'─'*18}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*6}  {'─'*5}  {'─'*4}")

for i, t in enumerate(new_oos_v2):
    r, bars, reason = sim_stale_exit(t, 8, 0.5)
    equity += r
    peak = max(peak, equity)
    dd = peak - equity
    dt = t['entry_dt'].strftime('%Y-%m-%d %H:%M')
    print(f"  {i+1:>4}  {t['pair']:>8}  {t['dir']:>4}  {dt:>18}  {r:>+6.2f}  {equity:>+6.1f}  {dd:>4.1f}  "
          f"{reason:>6}  {t['orig_mfe']:>5.2f}  {bars:>4}")


# ═══════════════════════════════════════════════════════════
# SECTION 6: FINAL VERDICT
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 6: FINAL VERDICT")
print(W)

# Compare baseline vs stale on new OOS
base_s = stats([{'r': t['orig_r']} for t in new_oos_v2])
stale_results = []
stale_count = 0
for t in new_oos_v2:
    r, bars, reason = sim_stale_exit(t, 8, 0.5)
    stale_results.append({'r': r})
    if reason == "STALE": stale_count += 1
stale_s = stats(stale_results)

print(f"\n  New OOS (Jul-Sep 2026, 7 EUR pairs):")
print(f"  V2 Baseline:      {base_s['n']} trades  R={base_s['R']:+.1f}  PF={base_s['pf']:.2f}  DD={base_s['mdd']:.1f}  R/DD={base_s['rdd']:.2f}")
print(f"  + Stale S=8/0.5R: {stale_s['n']} trades  R={stale_s['R']:+.1f}  PF={stale_s['pf']:.2f}  DD={stale_s['mdd']:.1f}  R/DD={stale_s['rdd']:.2f}  ({stale_count} stale exits)")
print(f"  Delta:             R={stale_s['R']-base_s['R']:+.1f}  PF={stale_s['pf']-base_s['pf']:+.2f}  DD={stale_s['mdd']-base_s['mdd']:+.1f}")

improved = stale_s['R'] > base_s['R'] or (stale_s['R'] >= base_s['R'] and stale_s['mdd'] < base_s['mdd'])
if improved:
    print(f"\n  VERDICT: STALE EXIT VALIDATED on new OOS data.")
    print(f"  The S=8/0.5R stale exit improves (or maintains) performance on fresh unseen data.")
else:
    if abs(stale_s['R'] - base_s['R']) < 1.0:
        print(f"\n  VERDICT: STALE EXIT NEUTRAL on new OOS data.")
        print(f"  Small sample size — difference is within noise range.")
    else:
        print(f"\n  VERDICT: STALE EXIT DEGRADED on new OOS data.")
        print(f"  The strategy may not generalize to this time period.")

print(f"\n{W}")
print("  DONE")
print(W)
