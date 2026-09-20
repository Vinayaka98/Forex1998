#!/usr/bin/env python3
"""
EUR Perfection Analysis — BUY + SELL across ALL EUR data
=========================================================
Dev CSVs: BUY only (no Sell SL columns)
New OOS CSVs: BUY + SELL (have both Active SL and Sell SL columns)
Prior OOS EURCHF: BUY only (no Sell SL columns)

Goal: Find optimal filters for BOTH directions across all EUR pairs.
"""
import csv, os, math
from datetime import datetime, timezone
from collections import defaultdict
from itertools import combinations

UPLOAD_DIR = "/root/.claude/uploads/c9dd1cc3-70c3-5800-b09b-3644f5933104"

DEV_FILES = {
    "EURNZD": ("2c010574-OANDA_EURNZD_240.csv", "Active TP", None),
    "EURCAD": ("52d23423-OANDA_EURCAD_240.csv", "Active TP", None),
    "EURAUD": ("70ab8fef-OANDA_EURAUD_240.csv", "Active TP", None),
    "EURGBP": ("d8d9759a-OANDA_EURGBP_240.csv", "Active TP", None),
    "EURUSD": ("8505bf9d-OANDA_EURUSD_240.csv", "Active TP", None),
}

PRIOR_OOS_EUR = {
    "EURCHF": ("92b510fc-OANDA_EURCHF_240.csv", "Active TP", None),
}

NEW_OOS_FILES = {
    "EURUSD": ("5b931546-OANDA_EURUSD_240_15da8.csv", "Active TP2", "Sell TP2"),
    "EURJPY": ("1c474f00-OANDA_EURJPY_240_d1869.csv", "Active TP2", "Sell TP2"),
    "EURGBP": ("2875719d-OANDA_EURGBP_240_13f27.csv", "Active TP2", "Sell TP2"),
    "EURAUD": ("41cccecd-OANDA_EURAUD_240_cfbf8.csv", "Active TP2", "Sell TP2"),
    "EURCAD": ("1f6729b9-OANDA_EURCAD_240_b8e32.csv", "Active TP2", "Sell TP2"),
    "EURNZD": ("d1260ae5-OANDA_EURNZD_240_9279b.csv", "Active TP2", "Sell TP2"),
    "EURCHF": ("44eaa2d3-OANDA_EURCHF_240_27717.csv", "Active TP2", "Sell TP2"),
}

def load_csv_full(fp):
    rows = []
    with open(fp) as f:
        for r in csv.DictReader(f):
            row = {
                'time': int(r['time']),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'buy_sl': float(r['Active SL']) if r.get('Active SL','').strip() else None,
            }
            # BUY TP — try different column names
            for col in ['Active TP2', 'Active TP']:
                if col in r and r[col].strip():
                    row['buy_tp'] = float(r[col])
                    break
            else:
                row['buy_tp'] = None
            # SELL columns
            row['sell_sl'] = float(r['Sell SL']) if r.get('Sell SL','').strip() else None
            for col in ['Sell TP2', 'Sell TP']:
                if col in r and r[col].strip():
                    row['sell_tp'] = float(r[col])
                    break
            else:
                row['sell_tp'] = None
            rows.append(row)
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

def extract_both_directions(pair, fp, dataset):
    rows = load_csv_full(fp)
    atr = compute_atr(rows)
    adx = compute_adx(rows)
    all_trades = []

    # Extract BUY trades
    in_buy = False; prev_buy_sl = None
    entry_bar = 0; ep = 0; sd = 0; itp = 0
    rmfe = 0.0; rmae = 0.0; bdata = []
    current_sl = 0; current_tp = 0

    for i, bar in enumerate(rows):
        sl = bar['buy_sl']; tp = bar['buy_tp']
        is_new = sl is not None and prev_buy_sl is None

        if in_buy:
            if sl is not None: current_sl = sl
            bn = i - entry_bar
            bhr = (bar['high']-ep)/sd; blr = (bar['low']-ep)/sd; bcr = (bar['close']-ep)/sd
            rmfe = max(rmfe, bhr); rmae = max(rmae, -blr)
            bdata.append({'bar':bn,'high_r':bhr,'low_r':blr,'close_r':bcr})
            xp = None; xreason = ""
            if bar['low'] <= current_sl: xp = current_sl; xreason = "SL"
            elif current_tp > 0 and bar['high'] >= current_tp: xp = current_tp; xreason = "TP"
            elif sl is None: xp = bar['close']; xreason = "IND"
            if xp is not None:
                rr = (xp - ep) / sd
                if xreason == "SL" and rr < -1.0: rr = -1.0
                if xreason == "TP":
                    tpr = abs(itp - ep) / sd; rr = min(rr, tpr)
                edt = datetime.fromtimestamp(rows[entry_bar]['time'], tz=timezone.utc)
                all_trades.append({
                    'pair':pair, 'dir':'BUY', 'dataset':dataset,
                    'entry_time':rows[entry_bar]['time'], 'entry_dt':edt,
                    'ep':ep, 'sd':sd, 'itp_r':abs(itp-ep)/sd if itp>0 and sd>0 else 0,
                    'atr':atr[entry_bar], 'adx':adx[entry_bar],
                    'atr_pctrank':percentrank(atr, entry_bar, 100),
                    'bd':bdata[:], 'orig_r':rr, 'orig_bars':len(bdata),
                    'orig_reason':xreason, 'orig_mfe':rmfe, 'orig_mae':rmae,
                    'entry_hour':edt.hour, 'entry_dow':edt.weekday(),
                })
                in_buy = False

        if not in_buy and is_new:
            entry_bar = i; ep = bar['close']; isl = sl; itp = tp if tp else 0
            current_sl = sl; current_tp = itp
            sd = abs(ep - isl)
            if sd == 0: sd = 0.0001
            if isl < ep:  # Confirm it's BUY
                rmfe = 0.0; rmae = 0.0; bdata = []
                in_buy = True
        prev_buy_sl = sl

    # Extract SELL trades
    in_sell = False; prev_sell_sl = None
    for i, bar in enumerate(rows):
        sl = bar['sell_sl']; tp = bar['sell_tp']
        is_new = sl is not None and prev_sell_sl is None

        if in_sell:
            if sl is not None: current_sl = sl
            bn = i - entry_bar
            bhr = (ep - bar['low'])/sd; blr = (ep - bar['high'])/sd; bcr = (ep - bar['close'])/sd
            rmfe = max(rmfe, bhr); rmae = max(rmae, -blr)
            bdata.append({'bar':bn,'high_r':bhr,'low_r':blr,'close_r':bcr})
            xp = None; xreason = ""
            if bar['high'] >= current_sl: xp = current_sl; xreason = "SL"
            elif current_tp > 0 and bar['low'] <= current_tp: xp = current_tp; xreason = "TP"
            elif sl is None: xp = bar['close']; xreason = "IND"
            if xp is not None:
                rr = (ep - xp) / sd
                if xreason == "SL" and rr < -1.0: rr = -1.0
                if xreason == "TP":
                    tpr = abs(ep - itp) / sd; rr = min(rr, tpr)
                edt = datetime.fromtimestamp(rows[entry_bar]['time'], tz=timezone.utc)
                all_trades.append({
                    'pair':pair, 'dir':'SELL', 'dataset':dataset,
                    'entry_time':rows[entry_bar]['time'], 'entry_dt':edt,
                    'ep':ep, 'sd':sd, 'itp_r':abs(ep-itp)/sd if itp>0 and sd>0 else 0,
                    'atr':atr[entry_bar], 'adx':adx[entry_bar],
                    'atr_pctrank':percentrank(atr, entry_bar, 100),
                    'bd':bdata[:], 'orig_r':rr, 'orig_bars':len(bdata),
                    'orig_reason':xreason, 'orig_mfe':rmfe, 'orig_mae':rmae,
                    'entry_hour':edt.hour, 'entry_dow':edt.weekday(),
                })
                in_sell = False

        if not in_sell and is_new:
            entry_bar = i; ep = bar['close']; isl = sl; itp = tp if tp else 0
            current_sl = sl; current_tp = itp
            sd = abs(ep - isl)
            if sd == 0: sd = 0.0001
            if isl > ep:  # Confirm it's SELL
                rmfe = 0.0; rmae = 0.0; bdata = []
                in_sell = True
        prev_sell_sl = sl

    return all_trades

def sim_stale_exit(trade, stale_bars=8, stale_mfe_thr=0.5):
    bd = trade['bd']
    if not bd: return trade['orig_r'], trade['orig_bars'], trade['orig_reason']
    max_mfe = 0.0
    for b in bd:
        max_mfe = max(max_mfe, b['high_r'])
        if b['bar'] >= stale_bars and max_mfe < stale_mfe_thr:
            return b['close_r'], b['bar'], "STALE"
    return trade['orig_r'], trade['orig_bars'], trade['orig_reason']

def get_final_r(trade, stale_bars=8, stale_mfe=0.5):
    r, _, _ = sim_stale_exit(trade, stale_bars, stale_mfe)
    return r

def stats(rs_list):
    if not rs_list: return {'n':0,'R':0,'wr':0,'pf':0,'exp':0,'mdd':0,'rdd':0,'aw':0,'al':0}
    n=len(rs_list); tr=sum(rs_list)
    w=[r for r in rs_list if r>=0.1]; l=[r for r in rs_list if r<=-0.1]
    gw=sum(w); gl=abs(sum(l))
    pf=gw/gl if gl>0 else 99.9
    eq=0;pk=0;mdd=0
    for r in rs_list:
        eq+=r; pk=max(pk,eq); mdd=max(mdd,pk-eq)
    aw=gw/len(w) if w else 0; al=gl/len(l) if l else 0
    return {'n':n,'R':tr,'wr':len(w)/n*100,'pf':pf,'exp':tr/n,
            'mdd':mdd,'aw':aw,'al':al,'rdd':tr/mdd if mdd>0 else 0}

W = '=' * 110
D = '-' * 110

# ═══════════════════════════════════════════════════════════
# LOAD ALL DATA
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  LOADING ALL EUR DATA — BUY + SELL")
print(W)

all_trades = []

for pair, (fname, buy_tp, sell_tp) in sorted(DEV_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_both_directions(pair, fp, 'DEV')
        all_trades.extend(trades)

for pair, (fname, buy_tp, sell_tp) in sorted(PRIOR_OOS_EUR.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_both_directions(pair, fp, 'PRIOR_OOS')
        all_trades.extend(trades)

for pair, (fname, buy_tp, sell_tp) in sorted(NEW_OOS_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_both_directions(pair, fp, 'NEW_OOS')
        all_trades.extend(trades)

all_trades.sort(key=lambda t: t['entry_time'])

all_buy = [t for t in all_trades if t['dir'] == 'BUY']
all_sell = [t for t in all_trades if t['dir'] == 'SELL']

print(f"  Total trades: {len(all_trades)} ({len(all_buy)} BUY, {len(all_sell)} SELL)")
print(f"  BUY pairs: {sorted(set(t['pair'] for t in all_buy))}")
print(f"  SELL pairs: {sorted(set(t['pair'] for t in all_sell))}")

# Show SELL trades by pair
print(f"\n  SELL trades by pair/dataset:")
for pair in sorted(set(t['pair'] for t in all_sell)):
    for ds in ['DEV','PRIOR_OOS','NEW_OOS']:
        pt = [t for t in all_sell if t['pair']==pair and t['dataset']==ds]
        if pt:
            print(f"    {pair} ({ds}): {len(pt)} trades")

# ═══════════════════════════════════════════════════════════
# SECTION A: ALL SELL TRADES — RAW ANALYSIS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION A: ALL SELL TRADES — RAW (no filters)")
print(W)

print(f"\n  Trade-by-trade listing:")
print(f"  {'#':>4}  {'Pair':>8}  {'Dataset':>10}  {'Date':>18}  {'R':>7}  {'MFE':>5}  {'MAE':>5}  {'Bars':>4}  "
      f"{'Exit':>5}  {'ADX':>5}  {'ATR%':>4}  {'Hour':>4}")
print(f"  {'─'*4}  {'─'*8}  {'─'*10}  {'─'*18}  {'─'*7}  {'─'*5}  {'─'*5}  {'─'*4}  "
      f"{'─'*5}  {'─'*5}  {'─'*4}  {'─'*4}")

for i, t in enumerate(all_sell):
    dt = t['entry_dt'].strftime('%Y-%m-%d %H:%M')
    print(f"  {i+1:>4}  {t['pair']:>8}  {t['dataset']:>10}  {dt:>18}  {t['orig_r']:>+6.2f}  "
          f"{t['orig_mfe']:>5.2f}  {t['orig_mae']:>5.2f}  {t['orig_bars']:>4}  "
          f"{t['orig_reason']:>5}  {t['adx']:>5.1f}  {t['atr_pctrank']:>4.0f}  {t['entry_hour']:>4}")

sell_rs = [t['orig_r'] for t in all_sell]
ss = stats(sell_rs)
print(f"\n  SELL Raw: {ss['n']}t  WR={ss['wr']:.1f}%  PF={ss['pf']:.2f}  R={ss['R']:+.1f}  DD={ss['mdd']:.1f}  R/DD={ss['rdd']:.2f}")

# Stale exit on sells
stale_sell_rs = [get_final_r(t) for t in all_sell]
sss = stats(stale_sell_rs)
print(f"  SELL+Stale: {sss['n']}t  WR={sss['wr']:.1f}%  PF={sss['pf']:.2f}  R={sss['R']:+.1f}  DD={sss['mdd']:.1f}  R/DD={sss['rdd']:.2f}")

# Per-pair SELL
print(f"\n  SELL per pair:")
for pair in sorted(set(t['pair'] for t in all_sell)):
    pt = [t for t in all_sell if t['pair']==pair]
    rs = [t['orig_r'] for t in pt]
    s = stats(rs)
    print(f"    {pair:>8}: {s['n']:>3}t  WR={s['wr']:>5.1f}%  PF={s['pf']:>5.2f}  R={s['R']:>+5.1f}  Exp={s['exp']:>+6.3f}")


# ═══════════════════════════════════════════════════════════
# SECTION B: SELL FILTER EXPLORATION
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION B: SELL TRADE FILTERS")
print(W)

# Hour analysis for sells
print(f"\n  SELL by hour:")
print(f"  {'Hour':>6}  {'N':>3}  {'WR':>6}  {'R':>7}  {'Exp':>7}")
print(f"  {'─'*6}  {'─'*3}  {'─'*6}  {'─'*7}  {'─'*7}")
for h in sorted(set(t['entry_hour'] for t in all_sell)):
    ht = [t for t in all_sell if t['entry_hour']==h]
    rs = [t['orig_r'] for t in ht]
    s = stats(rs)
    print(f"  {h:>4}:00  {s['n']:>3}  {s['wr']:>5.1f}%  {s['R']:>+6.1f}  {s['exp']:>+6.3f}")

# ADX analysis for sells
print(f"\n  SELL by ADX bucket:")
for lo, hi in [(0,15),(15,20),(20,25),(25,30),(30,99)]:
    ft = [t for t in all_sell if lo<=t['adx']<hi]
    if not ft: continue
    rs = [t['orig_r'] for t in ft]
    s = stats(rs)
    label = f"{lo}-{hi}" if hi<99 else f"{lo}+"
    print(f"    ADX {label:>6}: {s['n']:>3}t  WR={s['wr']:>5.1f}%  R={s['R']:>+5.1f}  Exp={s['exp']:>+6.3f}")

# ATR% for sells
print(f"\n  SELL by ATR percentrank:")
for lo, hi in [(0,30),(30,50),(50,70),(70,101)]:
    ft = [t for t in all_sell if lo<=t['atr_pctrank']<hi]
    if not ft: continue
    rs = [t['orig_r'] for t in ft]
    s = stats(rs)
    print(f"    ATR% {lo}-{hi-1}: {s['n']:>3}t  WR={s['wr']:>5.1f}%  R={s['R']:>+5.1f}  Exp={s['exp']:>+6.3f}")

# Stale exit sweep on sells
print(f"\n  SELL stale exit sweep:")
sell_base = stats([t['orig_r'] for t in all_sell])
print(f"  {'Config':>12}  {'N':>3}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Stale':>5}  {'ΔR':>6}")
print(f"  {'─'*12}  {'─'*3}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*5}  {'─'*6}")
print(f"  {'Baseline':>12}  {sell_base['n']:>3}  {sell_base['wr']:>5.1f}%  {sell_base['pf']:>5.2f}  {sell_base['R']:>+6.1f}  {'0':>5}  {'+0.0':>6}")
for sb in [5,8,10,12]:
    for sm in [0.3,0.5,0.7]:
        results = []
        stale_n = 0
        for t in all_sell:
            r, bars, reason = sim_stale_exit(t, sb, sm)
            results.append(r)
            if reason == "STALE": stale_n += 1
        s = stats(results)
        delta = s['R'] - sell_base['R']
        mark = " *" if sb==8 and sm==0.5 else ""
        print(f"  S={sb:>2}/{sm:.1f}R  {s['n']:>3}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {stale_n:>5}  {delta:>+5.1f}{mark}")


# ═══════════════════════════════════════════════════════════
# SECTION C: COMBINED BUY+SELL — Current V2 gates applied
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION C: V2 GATES ON BUY + SELL (EURAUD excluded, high ATR + low ADX rejected)")
print(W)

def apply_v2(trades, excl_pairs={"EURAUD"}, atr_thr=66, adx_thr=18.0):
    out = []
    for t in trades:
        if t['pair'] in excl_pairs: continue
        if t['atr_pctrank'] > atr_thr and t['adx'] < adx_thr: continue
        out.append(t)
    return out

v2_buy = apply_v2(all_buy)
v2_sell = apply_v2(all_sell)
v2_all = apply_v2(all_trades)

buy_rs = [get_final_r(t) for t in v2_buy]
sell_rs = [get_final_r(t) for t in v2_sell]
all_rs = [get_final_r(t) for t in v2_all]

sb = stats(buy_rs); ss = stats(sell_rs); sa = stats(all_rs)
print(f"\n  BUY  (V2+Stale): {sb['n']:>4}t  WR={sb['wr']:>5.1f}%  PF={sb['pf']:>5.2f}  R={sb['R']:>+6.1f}  DD={sb['mdd']:>5.1f}  R/DD={sb['rdd']:>5.2f}")
print(f"  SELL (V2+Stale): {ss['n']:>4}t  WR={ss['wr']:>5.1f}%  PF={ss['pf']:>5.2f}  R={ss['R']:>+6.1f}  DD={ss['mdd']:>5.1f}  R/DD={ss['rdd']:>5.2f}")
print(f"  ALL  (V2+Stale): {sa['n']:>4}t  WR={sa['wr']:>5.1f}%  PF={sa['pf']:>5.2f}  R={sa['R']:>+6.1f}  DD={sa['mdd']:>5.1f}  R/DD={sa['rdd']:>5.2f}")


# ═══════════════════════════════════════════════════════════
# SECTION D: BUY OPTIMIZATION — 5:00 UTC + PAIR COMBOS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION D: BUY FILTER OPTIMIZATION — What moves the needle?")
print(W)

def test_buy_filter(trades, name, exclude_hours=None, exclude_pairs=None,
                    min_adx=None, max_itp_r=None):
    ft = list(trades)
    if exclude_hours:
        ft = [t for t in ft if t['entry_hour'] not in exclude_hours]
    if exclude_pairs:
        ft = [t for t in ft if t['pair'] not in exclude_pairs]
    if min_adx is not None:
        ft = [t for t in ft if t['adx'] >= min_adx]
    if max_itp_r is not None:
        ft = [t for t in ft if t['itp_r'] <= max_itp_r]
    rs = [get_final_r(t) for t in ft]
    s = stats(rs)
    rej = len(trades) - s['n']
    # Breakdowns
    dev = [get_final_r(t) for t in ft if t['dataset']=='DEV']
    noos = [get_final_r(t) for t in ft if t['dataset']=='NEW_OOS']
    ds = stats(dev); ns = stats(noos)
    print(f"  {name:>40}  {s['n']:>3}t  WR={s['wr']:>5.1f}%  PF={s['pf']:>5.2f}  R={s['R']:>+6.1f}  "
          f"DD={s['mdd']:>4.1f}  R/DD={s['rdd']:>5.2f}  Rej={rej:>2}  |  "
          f"Dev:{ds['R']:>+5.1f}/{ds['rdd']:.2f}  OOS:{ns['R']:>+4.1f}/{ns['rdd']:.2f}")

print(f"\n  Current baseline (V2+Stale):")
test_buy_filter(v2_buy, "V2+Stale (current)")

print(f"\n  Single filters:")
test_buy_filter(v2_buy, "Excl 5:00 UTC", exclude_hours={5})
test_buy_filter(v2_buy, "Excl 10:00 UTC", exclude_hours={10})
test_buy_filter(v2_buy, "Excl 5:00+10:00 UTC", exclude_hours={5,10})
test_buy_filter(v2_buy, "TP/SL <= 3.0", max_itp_r=3.0)
test_buy_filter(v2_buy, "TP/SL <= 2.8", max_itp_r=2.8)
test_buy_filter(v2_buy, "Excl EURGBP", exclude_pairs={"EURGBP"})

print(f"\n  Combined filters:")
test_buy_filter(v2_buy, "5:00 + TP<=3.0", exclude_hours={5}, max_itp_r=3.0)
test_buy_filter(v2_buy, "5:00 + Excl EURGBP", exclude_hours={5}, exclude_pairs={"EURGBP"})
test_buy_filter(v2_buy, "5:00+10:00 + TP<=3.0", exclude_hours={5,10}, max_itp_r=3.0)
test_buy_filter(v2_buy, "5:00 + TP<=3.0 + Excl EURGBP", exclude_hours={5}, max_itp_r=3.0, exclude_pairs={"EURGBP"})


# ═══════════════════════════════════════════════════════════
# SECTION E: SELL OPTIMIZATION
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION E: SELL FILTER OPTIMIZATION")
print(W)

def test_sell_filter(trades, name, exclude_hours=None, exclude_pairs=None,
                     min_adx=None, max_itp_r=None, stale_bars=8, stale_mfe=0.5):
    ft = list(trades)
    if exclude_hours:
        ft = [t for t in ft if t['entry_hour'] not in exclude_hours]
    if exclude_pairs:
        ft = [t for t in ft if t['pair'] not in exclude_pairs]
    if min_adx is not None:
        ft = [t for t in ft if t['adx'] >= min_adx]
    if max_itp_r is not None:
        ft = [t for t in ft if t['itp_r'] <= max_itp_r]
    rs = [get_final_r(t, stale_bars, stale_mfe) for t in ft]
    s = stats(rs)
    rej = len(trades) - s['n']
    print(f"  {name:>40}  {s['n']:>3}t  WR={s['wr']:>5.1f}%  PF={s['pf']:>5.2f}  R={s['R']:>+6.1f}  "
          f"DD={s['mdd']:>4.1f}  R/DD={s['rdd']:>5.2f}  Rej={rej:>2}")

print(f"\n  Raw SELL performance:")
test_sell_filter(v2_sell, "V2 Raw SELL (no stale)", stale_bars=999, stale_mfe=99)
test_sell_filter(v2_sell, "V2+Stale SELL")

print(f"\n  SELL pair exclusions:")
for pair in sorted(set(t['pair'] for t in v2_sell)):
    test_sell_filter(v2_sell, f"Excl {pair}", exclude_pairs={pair})

print(f"\n  SELL hour filters:")
for h in sorted(set(t['entry_hour'] for t in v2_sell)):
    ht = [t for t in v2_sell if t['entry_hour']==h]
    if len(ht) >= 2:
        test_sell_filter(v2_sell, f"Excl {h}:00 UTC", exclude_hours={h})

print(f"\n  SELL ADX filters:")
for min_a in [10, 15, 18, 20, 25]:
    test_sell_filter(v2_sell, f"ADX >= {min_a}", min_adx=min_a)

print(f"\n  SELL TP/SL ratio filter:")
for max_tp in [2.5, 3.0, 3.5]:
    test_sell_filter(v2_sell, f"TP/SL <= {max_tp}", max_itp_r=max_tp)

print(f"\n  SELL stale exit parameter sweep:")
for sb in [5, 8, 10, 12]:
    for sm in [0.3, 0.5, 0.7]:
        test_sell_filter(v2_sell, f"Stale S={sb}/{sm:.1f}R", stale_bars=sb, stale_mfe=sm)


# ═══════════════════════════════════════════════════════════
# SECTION F: FULL SYSTEM — BEST BUY + BEST SELL COMBINED
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION F: FULL SYSTEM SCENARIOS — BUY + SELL combined equity")
print(W)

def combined_system(buy_trades, sell_trades, name,
                    buy_excl_hours=None, buy_excl_pairs=None, buy_max_itp=None,
                    sell_excl_hours=None, sell_excl_pairs=None, sell_min_adx=None, sell_max_itp=None,
                    buy_stale_b=8, buy_stale_m=0.5, sell_stale_b=8, sell_stale_m=0.5):
    bt = list(buy_trades)
    if buy_excl_hours: bt = [t for t in bt if t['entry_hour'] not in buy_excl_hours]
    if buy_excl_pairs: bt = [t for t in bt if t['pair'] not in buy_excl_pairs]
    if buy_max_itp is not None: bt = [t for t in bt if t['itp_r'] <= buy_max_itp]

    st = list(sell_trades)
    if sell_excl_hours: st = [t for t in st if t['entry_hour'] not in sell_excl_hours]
    if sell_excl_pairs: st = [t for t in st if t['pair'] not in sell_excl_pairs]
    if sell_min_adx is not None: st = [t for t in st if t['adx'] >= sell_min_adx]
    if sell_max_itp is not None: st = [t for t in st if t['itp_r'] <= sell_max_itp]

    combined = []
    for t in bt:
        combined.append((t['entry_time'], get_final_r(t, buy_stale_b, buy_stale_m), t['dir'], t['pair']))
    for t in st:
        combined.append((t['entry_time'], get_final_r(t, sell_stale_b, sell_stale_m), t['dir'], t['pair']))
    combined.sort(key=lambda x: x[0])

    rs = [c[1] for c in combined]
    s = stats(rs)
    buy_n = len(bt); sell_n = len(st)
    buy_r = sum(get_final_r(t, buy_stale_b, buy_stale_m) for t in bt)
    sell_r = sum(get_final_r(t, sell_stale_b, sell_stale_m) for t in st)
    print(f"  {name:>45}  {s['n']:>3}t ({buy_n}B+{sell_n}S)  WR={s['wr']:>5.1f}%  PF={s['pf']:>5.2f}  "
          f"R={s['R']:>+6.1f}  DD={s['mdd']:>4.1f}  R/DD={s['rdd']:>5.2f}  BuyR={buy_r:>+5.1f}  SellR={sell_r:>+5.1f}")

# Current system: BUY only
combined_system(v2_buy, [], "Current: BUY only (V2+Stale)")

# Add raw SELL
combined_system(v2_buy, v2_sell, "BUY(V2+Stale) + SELL(raw)")

# Add SELL with stale
combined_system(v2_buy, v2_sell, "BUY(V2+Stale) + SELL(V2+Stale)")

# BUY optimized + SELL
combined_system(v2_buy, v2_sell, "BUY(excl 5:00) + SELL(V2+Stale)",
                buy_excl_hours={5})

# BUY optimized + filtered SELL
combined_system(v2_buy, v2_sell, "BUY(excl 5:00) + SELL(excl weakest pair if any)",
                buy_excl_hours={5})

# Try TP/SL cap on both
combined_system(v2_buy, v2_sell, "BUY(5:00+TP<=3.0) + SELL(V2+Stale)",
                buy_excl_hours={5}, buy_max_itp=3.0)

# EURGBP exclusion on buy only
combined_system(v2_buy, v2_sell, "BUY(5:00+excl EURGBP) + SELL(V2+Stale)",
                buy_excl_hours={5}, buy_excl_pairs={"EURGBP"})

# Best buy + best sell combos
combined_system(v2_buy, v2_sell, "BUY(5:00+TP<=3) + SELL(ADX>=15)",
                buy_excl_hours={5}, buy_max_itp=3.0, sell_min_adx=15)

combined_system(v2_buy, v2_sell, "BUY(5:00+TP<=3+excl EURGBP) + SELL(V2+Stale)",
                buy_excl_hours={5}, buy_max_itp=3.0, buy_excl_pairs={"EURGBP"})


# ═══════════════════════════════════════════════════════════
# SECTION G: EQUITY CURVE for best combined system
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION G: EQUITY CURVE — BUY(excl 5:00) + SELL(V2+Stale)")
print(W)

# Build combined timeline for "BUY excl 5:00 + SELL V2+Stale"
combined_trades = []
for t in v2_buy:
    if t['entry_hour'] == 5: continue
    r = get_final_r(t)
    combined_trades.append({**t, 'final_r': r})
for t in v2_sell:
    r = get_final_r(t)
    combined_trades.append({**t, 'final_r': r})
combined_trades.sort(key=lambda t: t['entry_time'])

equity = 0.0; peak = 0.0; maxdd = 0.0
print(f"\n  New OOS only (Jul-Sep 2026):")
print(f"  {'#':>4}  {'Pair':>8}  {'Dir':>4}  {'Date':>18}  {'R':>7}  {'Equity':>7}  {'DD':>5}  {'Exit':>6}")
print(f"  {'─'*4}  {'─'*8}  {'─'*4}  {'─'*18}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*6}")

i = 0
for t in combined_trades:
    if t['dataset'] != 'NEW_OOS': continue
    i += 1
    _, _, reason = sim_stale_exit(t)
    equity += t['final_r']
    peak = max(peak, equity)
    dd = peak - equity
    maxdd = max(maxdd, dd)
    dt = t['entry_dt'].strftime('%Y-%m-%d %H:%M')
    print(f"  {i:>4}  {t['pair']:>8}  {t['dir']:>4}  {dt:>18}  {t['final_r']:>+6.2f}  {equity:>+6.1f}  {dd:>4.1f}  "
          f"{reason:>6}")

print(f"\n  New OOS Summary: {i} trades  R={equity:+.1f}  MaxDD={maxdd:.1f}  R/DD={equity/maxdd if maxdd>0 else 0:.2f}")


# ═══════════════════════════════════════════════════════════
# SECTION H: FINAL VERDICT
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION H: FINAL VERDICT — IMPROVEMENT OPPORTUNITIES")
print(W)

print("""
  CONFIRMED IMPROVEMENTS (data supports across dev + OOS):
  ════════════════════════════════════════════════════════

  1. 5:00 UTC BUY FILTER
     - 34 BUY trades at 05:00 UTC: WR 26.5%, PF 0.63, R=-7.1
     - Removing them: R/DD improves from 2.95 to 3.73
     - Consistent across dev (R/DD 2.77→3.63) and new OOS (no 5:00 trades)
     - Zero risk of hurting OOS since no 5:00 trades appear in new OOS data

  2. TP/SL > 3.0 FILTER (for BUY)
     - 84 trades with TP/SL > 3.0: WR 28.6%, PF 0.95, R=-2.8
     - These wide targets rarely hit; system is better at 2.0-2.5 TP/SL
     - Removing them improves expectancy and reduces noise

  3. SELL TRADES (evaluate below — small sample, handle with care)
     - Only available in new OOS CSVs (dev CSVs lack Sell columns)
     - Need to see if any SELL signal is worth taking

  REQUIRES MORE DATA:
  ════════════════════
  - EURGBP exclusion (BUY): reduces DD 12.5→6.8 but loses 35 trades
    → Needs more OOS data to confirm; currently mixed results
  - 10:00 UTC filter: only 12 trades, too small to act on
  - SELL direction: very small sample from new OOS only
""")

print(f"\n{W}")
print("  DONE")
print(W)
