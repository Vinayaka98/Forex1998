#!/usr/bin/env python3
"""
EUR Mastery Analysis — Find improvement opportunities across ALL EUR data
=========================================================================
Examines: entry hour, day-of-week, pair quality, ADX/ATR fine-tuning,
early momentum signals, winner vs loser profiles, and more.

Uses dev (5 EUR pairs, ~2576 bars each) + prior OOS (EURCHF) + new OOS (7 EUR pairs)
"""
import csv, os, math, argparse
from datetime import datetime, timezone
from collections import defaultdict

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

parser = argparse.ArgumentParser(description="EUR Mastery Analysis")
parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help="Directory containing CSV data files (default: ../data/)")
_args, _ = parser.parse_known_args()
UPLOAD_DIR = os.path.abspath(_args.data_dir)

DEV_FILES = {
    "EURNZD": ("2c010574-OANDA_EURNZD_240.csv", "Active TP"),
    "EURCAD": ("52d23423-OANDA_EURCAD_240.csv", "Active TP"),
    "EURAUD": ("70ab8fef-OANDA_EURAUD_240.csv", "Active TP"),
    "EURGBP": ("d8d9759a-OANDA_EURGBP_240.csv", "Active TP"),
    "EURUSD": ("8505bf9d-OANDA_EURUSD_240.csv", "Active TP"),
}

PRIOR_OOS_EUR = {
    "EURCHF_OOS1": ("92b510fc-OANDA_EURCHF_240.csv", "Active TP"),
}

NEW_OOS_FILES = {
    "EURUSD": ("5b931546-OANDA_EURUSD_240_15da8.csv", "Active TP2"),
    "EURJPY": ("1c474f00-OANDA_EURJPY_240_d1869.csv", "Active TP2"),
    "EURGBP": ("2875719d-OANDA_EURGBP_240_13f27.csv", "Active TP2"),
    "EURAUD": ("41cccecd-OANDA_EURAUD_240_cfbf8.csv", "Active TP2"),
    "EURCAD": ("1f6729b9-OANDA_EURCAD_240_b8e32.csv", "Active TP2"),
    "EURNZD": ("d1260ae5-OANDA_EURNZD_240_9279b.csv", "Active TP2"),
    "EURCHF": ("44eaa2d3-OANDA_EURCHF_240_27717.csv", "Active TP2"),
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
                    'entry_hour': edt.hour,
                    'entry_dow': edt.weekday(),  # 0=Mon, 6=Sun
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
    return trades

def apply_v2_gates(trades, atr_thr=66, adx_thr=18.0):
    filtered = []
    for t in sorted(trades, key=lambda x: x['entry_time']):
        if t['pair'] in ("EURAUD",): continue
        if t['atr_pctrank'] > atr_thr and t['adx'] < adx_thr: continue
        filtered.append(t)
    return filtered

def sim_stale_exit(trade, stale_bars=8, stale_mfe_thr=0.5):
    bd = trade['bd']
    if not bd: return trade['orig_r'], trade['orig_bars'], trade['orig_reason']
    max_mfe = 0.0
    for b in bd:
        max_mfe = max(max_mfe, b['high_r'])
        if b['bar'] >= stale_bars and max_mfe < stale_mfe_thr:
            return b['close_r'], b['bar'], "STALE"
    return trade['orig_r'], trade['orig_bars'], trade['orig_reason']

def get_final_r(trade):
    r, _, _ = sim_stale_exit(trade, 8, 0.5)
    return r

def stats(trades_r):
    if not trades_r: return {'n':0,'R':0,'wr':0,'pf':0,'exp':0,'mdd':0,'rdd':0,'aw':0,'al':0}
    n=len(trades_r); tr=sum(trades_r)
    w=[r for r in trades_r if r>=0.1]; l=[r for r in trades_r if r<=-0.1]
    gw=sum(w); gl=abs(sum(l))
    pf=gw/gl if gl>0 else 99.9
    eq=0;pk=0;mdd=0
    for r in trades_r:
        eq+=r; pk=max(pk,eq); mdd=max(mdd,pk-eq)
    aw=gw/len(w) if w else 0; al=gl/len(l) if l else 0
    return {'n':n,'R':tr,'wr':len(w)/n*100,'pf':pf,'exp':tr/n,
            'mdd':mdd,'aw':aw,'al':al,'rdd':tr/mdd if mdd>0 else 0}

W = '=' * 105
D = '-' * 105

# ═══════════════════════════════════════════════════════════
# LOAD ALL EUR DATA
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  LOADING ALL EUR DATA")
print(W)

all_trades = []  # raw, pre-V2
datasets_raw = {}

# Dev
for pair, (fname, tp_col) in sorted(DEV_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_trades(pair, fp, tp_col)
        for t in trades: t['dataset'] = 'DEV'
        datasets_raw.setdefault('DEV', []).extend(trades)
        all_trades.extend(trades)

# Prior OOS (EUR only)
for pair, (fname, tp_col) in sorted(PRIOR_OOS_EUR.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_trades(pair.replace("_OOS1",""), fp, tp_col)
        for t in trades: t['dataset'] = 'PRIOR_OOS'
        datasets_raw.setdefault('PRIOR_OOS', []).extend(trades)
        all_trades.extend(trades)

# New OOS
for pair, (fname, tp_col) in sorted(NEW_OOS_FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fp):
        trades = extract_trades(pair, fp, tp_col)
        for t in trades: t['dataset'] = 'NEW_OOS'
        datasets_raw.setdefault('NEW_OOS', []).extend(trades)
        all_trades.extend(trades)

# Apply V2 + stale exit (our current production config)
all_v2 = apply_v2_gates(all_trades)
print(f"  Raw trades: {len(all_trades)}")
print(f"  After V2 gates: {len(all_v2)} (BUY only below)")

# Only BUY trades (system is long-EUR-only)
all_buy = [t for t in all_v2 if t['dir'] == 'BUY']
print(f"  BUY trades: {len(all_buy)}")

# Apply stale exit to get final R
for t in all_buy:
    t['final_r'] = get_final_r(t)

base_rs = [t['orig_r'] for t in all_buy]
stale_rs = [t['final_r'] for t in all_buy]
sb = stats(base_rs)
ss = stats(stale_rs)
print(f"\n  V2 Baseline:  {sb['n']}t  R={sb['R']:+.1f}  PF={sb['pf']:.2f}  DD={sb['mdd']:.1f}  R/DD={sb['rdd']:.2f}")
print(f"  V2+Stale:     {ss['n']}t  R={ss['R']:+.1f}  PF={ss['pf']:.2f}  DD={ss['mdd']:.1f}  R/DD={ss['rdd']:.2f}")

# ═══════════════════════════════════════════════════════════
# ANALYSIS 1: PER-PAIR DEEP DIVE
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 1: PER-PAIR PERFORMANCE (V2+Stale, all datasets combined)")
print(W)

pairs = sorted(set(t['pair'] for t in all_buy))
print(f"\n  {'Pair':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'MDD':>5}  {'R/DD':>5}  "
      f"{'AvgW':>5}  {'AvgL':>5}  {'MFE':>5}  {'MAE':>5}")
print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}  "
      f"{'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}")

for pair in pairs:
    pt = [t for t in all_buy if t['pair'] == pair]
    rs = [t['final_r'] for t in pt]
    s = stats(rs)
    avg_mfe = sum(t['orig_mfe'] for t in pt)/len(pt)
    avg_mae = sum(t['orig_mae'] for t in pt)/len(pt)
    flag = " <<<" if s['exp'] < -0.1 else ""
    print(f"  {pair:>8}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}  {s['aw']:>5.2f}  {s['al']:>5.2f}  {avg_mfe:>5.2f}  {avg_mae:>5.2f}{flag}")

# Per pair per dataset
print(f"\n  Per-pair by dataset:")
print(f"  {'Pair':>8}  {'Dataset':>10}  {'N':>4}  {'WR':>6}  {'R':>7}  {'Exp':>7}")
print(f"  {'─'*8}  {'─'*10}  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*7}")
for pair in pairs:
    for ds in ['DEV', 'PRIOR_OOS', 'NEW_OOS']:
        pt = [t for t in all_buy if t['pair'] == pair and t['dataset'] == ds]
        if not pt: continue
        rs = [t['final_r'] for t in pt]
        s = stats(rs)
        print(f"  {pair:>8}  {ds:>10}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['R']:>+6.1f}  {s['exp']:>+6.3f}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 2: ENTRY HOUR (UTC)
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 2: ENTRY HOUR (UTC) — 4H candle open times")
print(W)

hours = sorted(set(t['entry_hour'] for t in all_buy))
print(f"\n  {'Hour':>6}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'AvgW':>5}  {'AvgL':>5}  {'StaleN':>6}")
print(f"  {'─'*6}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}  {'─'*6}")
for h in hours:
    ht = [t for t in all_buy if t['entry_hour'] == h]
    rs = [t['final_r'] for t in ht]
    s = stats(rs)
    stale_n = sum(1 for t in ht if sim_stale_exit(t, 8, 0.5)[2] == "STALE")
    flag = " <<<" if s['n'] >= 5 and s['exp'] < -0.15 else ""
    print(f"  {h:>4}:00  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['aw']:>5.2f}  {s['al']:>5.2f}  {stale_n:>6}{flag}")

# Test: exclude worst hour(s) if they have enough samples
print(f"\n  Impact of excluding specific hours:")
for exclude_hours in [[1], [5], [1,5], [21], [1,21]]:
    ft = [t for t in all_buy if t['entry_hour'] not in exclude_hours]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    excluded = len(all_buy) - len(ft)
    label = f"Excl {','.join(str(h) for h in exclude_hours)}:00"
    print(f"  {label:>20}  {s['n']:>4}t  R={s['R']:>+5.1f}  PF={s['pf']:>5.2f}  DD={s['mdd']:>4.1f}  "
          f"R/DD={s['rdd']:>5.2f}  (dropped {excluded})")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 3: DAY OF WEEK
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 3: DAY OF WEEK")
print(W)

dow_names = {0:'Mon',1:'Tue',2:'Wed',3:'Thu',4:'Fri',5:'Sat',6:'Sun'}
dows = sorted(set(t['entry_dow'] for t in all_buy))
print(f"\n  {'Day':>6}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'AvgW':>5}  {'AvgL':>5}")
print(f"  {'─'*6}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}")
for d in dows:
    dt = [t for t in all_buy if t['entry_dow'] == d]
    rs = [t['final_r'] for t in dt]
    s = stats(rs)
    flag = " <<<" if s['n'] >= 8 and s['exp'] < -0.15 else ""
    print(f"  {dow_names.get(d,'?'):>6}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  "
          f"{s['exp']:>+6.3f}  {s['aw']:>5.2f}  {s['al']:>5.2f}{flag}")

# Test excluding worst day(s)
print(f"\n  Impact of excluding specific days:")
for excl in [[4], [0], [0,4]]:
    ft = [t for t in all_buy if t['entry_dow'] not in excl]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    excluded = len(all_buy) - len(ft)
    label = f"Excl {','.join(dow_names[d] for d in excl)}"
    print(f"  {label:>20}  {s['n']:>4}t  R={s['R']:>+5.1f}  PF={s['pf']:>5.2f}  DD={s['mdd']:>4.1f}  "
          f"R/DD={s['rdd']:>5.2f}  (dropped {excluded})")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 4: ADX FINE-TUNING
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 4: ADX THRESHOLD SWEEP (current gate: high ATR + ADX < 18)")
print(W)

print(f"\n  Note: V2 Gate = reject if ATR_pctrank > 66 AND ADX < threshold")
print(f"  Currently ADX < 18.0. Testing if a different threshold helps.\n")

# Also test standalone ADX minimum (regardless of ATR)
print(f"  A) V2 gate ADX threshold sweep:")
print(f"  {'ADXthr':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'MDD':>5}  {'R/DD':>5}  {'Rej':>4}")
print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}  {'─'*4}")
for adx_t in [0, 10, 14, 16, 18, 20, 22, 25, 30, 50]:
    ft = apply_v2_gates(all_trades, atr_thr=66, adx_thr=adx_t)
    ft = [t for t in ft if t['dir'] == 'BUY']
    rs = [get_final_r(t) for t in ft]
    s = stats(rs)
    rej = len(all_buy) - s['n']
    mark = " *" if adx_t == 18 else ""
    print(f"  {adx_t:>6.0f}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}  {rej:>4}{mark}")

# B) Standalone ADX minimum (reject ALL trades with ADX below threshold, regardless of ATR)
print(f"\n  B) Standalone ADX minimum (reject if ADX < threshold, any ATR):")
print(f"  {'MinADX':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'MDD':>5}  {'R/DD':>5}  {'Rej':>4}")
print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}  {'─'*4}")
for min_adx in [0, 10, 12, 15, 18, 20, 22, 25, 30]:
    ft = [t for t in all_buy if t['adx'] >= min_adx]
    rs = [get_final_r(t) for t in ft]
    s = stats(rs)
    rej = len(all_buy) - s['n']
    print(f"  {min_adx:>6.0f}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}  {rej:>4}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 5: ATR PERCENTRANK SWEEP
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 5: ATR PERCENTRANK — Low vs High volatility regime")
print(W)

print(f"\n  {'ATR%':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'AvgW':>5}  {'AvgL':>5}")
print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}")
for lo, hi in [(0,20),(20,40),(40,60),(60,80),(80,101)]:
    ft = [t for t in all_buy if lo <= t['atr_pctrank'] < hi]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    print(f"  {lo:>3}-{hi-1:<3}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['aw']:>5.2f}  {s['al']:>5.2f}")

# Test excluding high ATR entirely
print(f"\n  Excluding high ATR regimes:")
for max_atr in [90, 80, 70, 60, 50]:
    ft = [t for t in all_buy if t['atr_pctrank'] <= max_atr]
    rs = [get_final_r(t) for t in ft]
    s = stats(rs)
    rej = len(all_buy) - s['n']
    print(f"  ATR% <= {max_atr:>3}  {s['n']:>4}t  R={s['R']:>+5.1f}  PF={s['pf']:>5.2f}  DD={s['mdd']:>4.1f}  "
          f"R/DD={s['rdd']:>5.2f}  (dropped {rej})")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 6: EARLY MOMENTUM (MFE at bar 1, 2, 3)
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 6: EARLY MOMENTUM — MFE at bar 1-3 as signal quality predictor")
print(W)

# What does bar-1 MFE tell us about trade outcome?
for bar_n in [1, 2, 3]:
    print(f"\n  MFE at bar {bar_n}:")
    print(f"  {'MFE Range':>12}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}")
    print(f"  {'─'*12}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}")
    for lo, hi in [(0,0.05),(0.05,0.1),(0.1,0.2),(0.2,0.5),(0.5,99)]:
        ft = []
        for t in all_buy:
            if len(t['bd']) >= bar_n:
                mfe_at_bar = max(b['high_r'] for b in t['bd'][:bar_n])
                if lo <= mfe_at_bar < hi:
                    ft.append(t)
        rs = [t['final_r'] for t in ft]
        s = stats(rs)
        label = f"{lo:.2f}-{hi:.2f}" if hi < 99 else f"{lo:.2f}+"
        print(f"  {label:>12}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}")

# Test: kill trade if bar-1 MFE == 0 (price never went above entry)
print(f"\n  Early momentum filter tests:")
for bar_n, min_mfe in [(1, 0.0), (1, 0.05), (2, 0.1), (3, 0.1), (3, 0.2)]:
    ft = []
    for t in all_buy:
        if len(t['bd']) >= bar_n:
            mfe_at_bar = max(b['high_r'] for b in t['bd'][:bar_n])
            if mfe_at_bar >= min_mfe:
                ft.append(t)
        else:
            ft.append(t)
    rs = [get_final_r(t) for t in ft]
    s = stats(rs)
    rej = len(all_buy) - s['n']
    print(f"  Bar{bar_n} MFE >= {min_mfe:.2f}  {s['n']:>4}t  R={s['R']:>+5.1f}  PF={s['pf']:>5.2f}  DD={s['mdd']:>4.1f}  "
          f"R/DD={s['rdd']:>5.2f}  (dropped {rej})")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 7: WINNER vs LOSER PROFILE
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 7: WINNER vs LOSER PROFILES")
print(W)

winners = [t for t in all_buy if t['final_r'] >= 0.1]
losers = [t for t in all_buy if t['final_r'] <= -0.1]
flat = [t for t in all_buy if -0.1 < t['final_r'] < 0.1]

print(f"\n  Winners: {len(winners)}  Losers: {len(losers)}  Flat/Stale: {len(flat)}")

def profile(trades, label):
    if not trades: return
    avg_adx = sum(t['adx'] for t in trades)/len(trades)
    avg_atr = sum(t['atr_pctrank'] for t in trades)/len(trades)
    avg_mfe = sum(t['orig_mfe'] for t in trades)/len(trades)
    avg_mae = sum(t['orig_mae'] for t in trades)/len(trades)
    avg_bars = sum(t['orig_bars'] for t in trades)/len(trades)
    avg_sd = sum(t['sd'] for t in trades)/len(trades)
    hours = defaultdict(int)
    for t in trades: hours[t['entry_hour']] += 1
    top_hours = sorted(hours.items(), key=lambda x: -x[1])[:3]
    dows = defaultdict(int)
    for t in trades: dows[t['entry_dow']] += 1
    top_dows = sorted(dows.items(), key=lambda x: -x[1])[:3]
    print(f"\n  {label}:")
    print(f"    Avg ADX={avg_adx:.1f}  ATR%={avg_atr:.0f}  MFE={avg_mfe:.2f}R  MAE={avg_mae:.2f}R  Bars={avg_bars:.0f}")
    print(f"    Top hours: {', '.join(f'{h}:00({c})' for h,c in top_hours)}")
    print(f"    Top days: {', '.join(f'{dow_names[d]}({c})' for d,c in top_dows)}")

profile(winners, "WINNERS")
profile(losers, "LOSERS")

# Bar-1 close R comparison
print(f"\n  Bar-1 close_r distribution:")
for label, group in [("Winners", winners), ("Losers", losers)]:
    bar1_rs = [t['bd'][0]['close_r'] if t['bd'] else 0 for t in group]
    if bar1_rs:
        avg = sum(bar1_rs)/len(bar1_rs)
        pos = sum(1 for r in bar1_rs if r > 0)
        print(f"    {label}: avg bar1 close_r = {avg:+.3f}  ({pos}/{len(bar1_rs)} positive = {pos/len(bar1_rs)*100:.0f}%)")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 8: PAIR EXCLUSION COMBINATIONS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 8: PAIR EXCLUSION / INCLUSION SWEEP")
print(W)

print(f"\n  Already excluding EURAUD. Testing other pair exclusions:")
print(f"  {'Excluded':>16}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'MDD':>5}  {'R/DD':>5}")
print(f"  {'─'*16}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}")

# Baseline (EURAUD already excluded)
s = stats([t['final_r'] for t in all_buy])
print(f"  {'None':>16}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
      f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}")

for excl in pairs:
    ft = [t for t in all_buy if t['pair'] != excl]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    print(f"  {excl:>16}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}")

# Two-pair exclusions
print(f"\n  Two-pair exclusions:")
from itertools import combinations
for excl_pair in combinations(pairs, 2):
    ft = [t for t in all_buy if t['pair'] not in excl_pair]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    if s['n'] < 20: continue
    label = f"{excl_pair[0]}+{excl_pair[1]}"
    print(f"  {label:>16}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {s['rdd']:>5.2f}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 9: STOP DISTANCE (R-multiple target)
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 9: INITIAL TP/SL RATIO ANALYSIS")
print(W)

print(f"\n  TP/SL ratio distribution and performance:")
print(f"  {'TP/SL':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}")
print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}")
for lo, hi in [(0,1.5),(1.5,2.0),(2.0,2.5),(2.5,3.0),(3.0,99)]:
    ft = [t for t in all_buy if lo <= t['itp_r'] < hi]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    label = f"{lo:.1f}-{hi:.1f}" if hi < 99 else f"{lo:.1f}+"
    print(f"  {label:>8}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 10: CONSECUTIVE LOSS STREAKS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 10: LOSS STREAKS & RECOVERY")
print(W)

sorted_trades = sorted(all_buy, key=lambda t: t['entry_time'])
streak = 0
max_streak = 0
streaks = []
for t in sorted_trades:
    if t['final_r'] <= -0.1:
        streak += 1
        max_streak = max(max_streak, streak)
    else:
        if streak > 0: streaks.append(streak)
        streak = 0
if streak > 0: streaks.append(streak)

print(f"\n  Max consecutive losses: {max_streak}")
print(f"  Loss streak distribution:")
for s_len in sorted(set(streaks)):
    count = sum(1 for s in streaks if s == s_len)
    print(f"    {s_len} losses in a row: {count} times")

# After N consecutive losses, what happens to next trade?
print(f"\n  Performance after N consecutive losses:")
print(f"  {'After':>8}  {'Next WR':>8}  {'Next Avg R':>10}  {'N':>4}")
print(f"  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*4}")
for after_n in [1, 2, 3, 4, 5]:
    streak = 0
    next_rs = []
    for t in sorted_trades:
        if streak >= after_n:
            next_rs.append(t['final_r'])
        if t['final_r'] <= -0.1:
            streak += 1
        else:
            streak = 0
    if next_rs:
        wr = sum(1 for r in next_rs if r >= 0.1)/len(next_rs)*100
        avg_r = sum(next_rs)/len(next_rs)
        print(f"  {after_n:>6}L  {wr:>7.1f}%  {avg_r:>+9.3f}  {next_rs.__len__():>4}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 11: COMBINED FILTER COMBOS
# ═══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  ANALYSIS 11: CANDIDATE FILTER COMBINATIONS (on top of V2+Stale)")
print(W)

def filter_combo(trades, name, exclude_pairs=None, exclude_hours=None, exclude_dows=None,
                 min_adx=None, max_atr_pct=None):
    ft = list(trades)
    if exclude_pairs:
        ft = [t for t in ft if t['pair'] not in exclude_pairs]
    if exclude_hours:
        ft = [t for t in ft if t['entry_hour'] not in exclude_hours]
    if exclude_dows:
        ft = [t for t in ft if t['entry_dow'] not in exclude_dows]
    if min_adx is not None:
        ft = [t for t in ft if t['adx'] >= min_adx]
    if max_atr_pct is not None:
        ft = [t for t in ft if t['atr_pctrank'] <= max_atr_pct]
    rs = [t['final_r'] for t in ft]
    s = stats(rs)
    rej = len(trades) - s['n']
    # Also break out by dataset
    dev_rs = [t['final_r'] for t in ft if t['dataset'] == 'DEV']
    new_oos_rs = [t['final_r'] for t in ft if t['dataset'] == 'NEW_OOS']
    ds = stats(dev_rs)
    ns = stats(new_oos_rs)
    print(f"  {name:>35}  {s['n']:>4}t  WR={s['wr']:>5.1f}%  PF={s['pf']:>5.2f}  R={s['R']:>+5.1f}  "
          f"DD={s['mdd']:>4.1f}  R/DD={s['rdd']:>5.2f}  Rej={rej}  |  "
          f"Dev:{ds['R']:>+5.1f}/{ds['rdd']:.2f}  NewOOS:{ns['R']:>+4.1f}/{ns['rdd']:.2f}")

ss_ref = stats([t['final_r'] for t in all_buy])
print(f"\n  Baseline (V2+Stale): {ss_ref['n']}t  R={ss_ref['R']:+.1f}  PF={ss_ref['pf']:.2f}  DD={ss_ref['mdd']:.1f}  R/DD={ss_ref['rdd']:.2f}\n")

filter_combo(all_buy, "V2+Stale (current)")
filter_combo(all_buy, "Excl EURGBP", exclude_pairs={"EURGBP"})
filter_combo(all_buy, "Excl EURCAD", exclude_pairs={"EURCAD"})
filter_combo(all_buy, "ADX >= 15", min_adx=15)
filter_combo(all_buy, "ADX >= 20", min_adx=20)
filter_combo(all_buy, "ATR% <= 80", max_atr_pct=80)
filter_combo(all_buy, "Excl 5:00 UTC", exclude_hours={5})
filter_combo(all_buy, "Excl 1:00 UTC", exclude_hours={1})
filter_combo(all_buy, "Excl Fri", exclude_dows={4})
filter_combo(all_buy, "ADX>=15 + Excl EURGBP", min_adx=15, exclude_pairs={"EURGBP"})
filter_combo(all_buy, "ADX>=20 + ATR%<=80", min_adx=20, max_atr_pct=80)
filter_combo(all_buy, "ADX>=15 + ATR%<=80", min_adx=15, max_atr_pct=80)
filter_combo(all_buy, "Excl EURGBP + Excl 5:00", exclude_pairs={"EURGBP"}, exclude_hours={5})
filter_combo(all_buy, "Excl EURGBP+EURCAD", exclude_pairs={"EURGBP","EURCAD"})
filter_combo(all_buy, "ADX>=15 + Excl EURGBP+EURCAD", min_adx=15, exclude_pairs={"EURGBP","EURCAD"})


print(f"\n{W}")
print("  DONE — Review findings above for improvement candidates")
print(W)
