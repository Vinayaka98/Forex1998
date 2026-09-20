#!/usr/bin/env python3
"""
Forex1998 V3 Pro — Full Statistical Audit (V2 — corrected)
============================================================
Fixes from V1 and V2:
 - Degradation computed on AFTER-COST numbers (V1 used gross — was misleading)
 - Monte Carlo: block bootstrap resampling with replacement (V1 shuffle was
   trivially 100% — same total R)
 - Added bootstrap confidence interval for OOS expectancy (the key test)
 - Fixed "worst case" labeling — 1st percentile ≠ worst simulation
 - Pair differences reported as hypotheses, not established findings
 - Classification: "CANDIDATE EDGE" not "PROBABLE EDGE" — honest about
   what 109 OOS trades at +0.031R/trade can and cannot prove

Tests:
 1. In-sample / Out-of-sample split with full metrics
 2. Parameter sensitivity (wobble test for overfitting)
 3. Realistic costs: spread + commission + slippage
 4. Block Bootstrap Monte Carlo: 10,000 resampled trade sequences
 5. Final verdict: "looks profitable" vs "evidence behind it"
"""
import csv, os, math, random
from datetime import datetime, timezone
from collections import defaultdict

random.seed(42)

UPLOAD_DIR = "/root/.claude/uploads/c9dd1cc3-70c3-5800-b09b-3644f5933104"

# ── File Registry ──
# Format: (filename, tp_col, dataset_tag)
FILES = {
    # DEV (in-sample) — 5 EUR pairs, ~2576 bars each
    "EURNZD_DEV": ("2c010574-OANDA_EURNZD_240.csv", "Active TP", "DEV"),
    "EURCAD_DEV": ("52d23423-OANDA_EURCAD_240.csv", "Active TP", "DEV"),
    "EURAUD_DEV": ("70ab8fef-OANDA_EURAUD_240.csv", "Active TP", "DEV"),
    "EURGBP_DEV": ("d8d9759a-OANDA_EURGBP_240.csv", "Active TP", "DEV"),
    "EURUSD_DEV": ("8505bf9d-OANDA_EURUSD_240.csv", "Active TP", "DEV"),
    # Prior OOS — EURCHF OANDA + 5 BLACKBULL
    "EURCHF_OOS1": ("92b510fc-OANDA_EURCHF_240.csv", "Active TP", "OOS_PRIOR"),
    "BB_EURUSD":   ("3436718b-BLACKBULL_EURUSD_240.csv", "Active TP2", "OOS_PRIOR"),
    "BB_USDCAD":   ("1fb1e7cb-BLACKBULL_USDCAD_240.csv", "Active TP2", "OOS_PRIOR"),
    "BB_NZDUSD":   ("51a3ea58-BLACKBULL_NZDUSD_240.csv", "Active TP2", "OOS_PRIOR"),
    "BB_AUDUSD":   ("f91b48c9-BLACKBULL_AUDUSD_240.csv", "Active TP2", "OOS_PRIOR"),
    "BB_USDJPY":   ("e53fd9ee-BLACKBULL_USDJPY_240.csv", "Active TP2", "OOS_PRIOR"),
    # New OOS — 7 EUR pairs, ~300 bars each
    "EURUSD_OOS2":  ("5b931546-OANDA_EURUSD_240_15da8.csv", "Active TP2", "OOS_NEW"),
    "EURJPY_OOS2":  ("1c474f00-OANDA_EURJPY_240_d1869.csv", "Active TP2", "OOS_NEW"),
    "EURGBP_OOS2":  ("2875719d-OANDA_EURGBP_240_13f27.csv", "Active TP2", "OOS_NEW"),
    "EURAUD_OOS2":  ("41cccecd-OANDA_EURAUD_240_cfbf8.csv", "Active TP2", "OOS_NEW"),
    "EURCAD_OOS2":  ("1f6729b9-OANDA_EURCAD_240_b8e32.csv", "Active TP2", "OOS_NEW"),
    "EURNZD_OOS2":  ("d1260ae5-OANDA_EURNZD_240_9279b.csv", "Active TP2", "OOS_NEW"),
    "EURCHF_OOS2":  ("44eaa2d3-OANDA_EURCHF_240_27717.csv", "Active TP2", "OOS_NEW"),
}

# ── Realistic cost assumptions (per trade, in R-multiples) ──
# Typical 4H swing on EUR pairs:
#   Average stop distance ≈ 50 pips (varies by pair)
#   Spread: ~1.5 pips on EUR majors → 1.5/50 = 0.03R
#   Commission: ~$7 per 100k round trip → ~0.7 pips → 0.014R
#   Slippage: ~0.5 pips per entry+exit → 0.01R
COST_PER_TRADE_R = 0.054  # total realistic cost per trade in R

# Pessimistic scenario
COST_PESSIMISTIC_R = 0.08  # wider spread broker, worse fills


# ══════════════════════════════════════════════════════════
#  CORE ENGINE (same as validated backtest scripts)
# ══════════════════════════════════════════════════════════

def load_csv(fp, tp_col="Active TP2"):
    rows = []
    with open(fp) as f:
        for r in csv.DictReader(f):
            row = {
                'time': int(r['time']),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'sl': float(r['Active SL']) if r.get('Active SL','').strip() else None,
            }
            for col in [tp_col, 'Active TP2', 'Active TP']:
                if col in r and r[col].strip():
                    row['tp'] = float(r[col]); break
            else:
                row['tp'] = None
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
    return sum(1 for j in range(idx-length, idx) if series[j] < val)/length*100.0

def extract_trades(pair, fp, tp_col, dataset):
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
            if sl is not None: current_sl = sl
            bn = i - entry_bar
            direction = "BUY"
            bhr=(bar['high']-ep)/sd; blr=(bar['low']-ep)/sd; bcr=(bar['close']-ep)/sd
            rmfe=max(rmfe,bhr); rmae=max(rmae,-blr)
            bdata.append({'bar':bn,'high_r':bhr,'low_r':blr,'close_r':bcr})
            xp=None; xreason=""
            if bar['low']<=current_sl: xp=current_sl; xreason="SL"
            elif current_tp>0 and bar['high']>=current_tp: xp=current_tp; xreason="TP"
            elif sl is None: xp=bar['close']; xreason="IND"
            if xp is not None:
                rr=(xp-ep)/sd
                if xreason=="SL" and rr<-1.0: rr=-1.0
                if xreason=="TP":
                    tpr=abs(itp-ep)/sd; rr=min(rr,tpr)
                edt=datetime.fromtimestamp(rows[entry_bar]['time'],tz=timezone.utc)
                trades.append({
                    'pair':pair.split('_')[0] if '_' in pair else pair,
                    'label':pair, 'dir':'BUY', 'dataset':dataset,
                    'entry_time':rows[entry_bar]['time'], 'entry_dt':edt,
                    'ep':ep, 'sd':sd, 'itp_r':abs(itp-ep)/sd if itp>0 and sd>0 else 0,
                    'atr':atr[entry_bar], 'adx':adx[entry_bar],
                    'atr_pctrank':percentrank(atr, entry_bar, 100),
                    'bd':bdata[:], 'orig_r':rr, 'orig_bars':len(bdata),
                    'orig_reason':xreason, 'orig_mfe':rmfe, 'orig_mae':rmae,
                    'entry_hour':edt.hour, 'entry_dow':edt.weekday(),
                    'stop_pips': sd * 10000 if 'JPY' not in pair else sd * 100,
                })
                in_trade=False
        if not in_trade and is_new:
            entry_bar=i; ep=bar['close']; isl=sl; itp=tp if tp else 0
            current_sl=sl; current_tp=itp
            sd=abs(ep-isl)
            if sd==0: sd=0.0001
            if isl<ep:  # BUY only
                rmfe=0.0; rmae=0.0; bdata=[]
                in_trade=True
        prev_sl=sl
    return trades

def apply_v2(trades, atr_thr=66, adx_thr=18.0, excl_pairs=None):
    if excl_pairs is None: excl_pairs = {"EURAUD"}
    return [t for t in trades
            if t['pair'] not in excl_pairs
            and not (t['atr_pctrank'] > atr_thr and t['adx'] < adx_thr)]

def sim_stale(trade, sb=8, sm=0.5):
    bd = trade['bd']
    if not bd: return trade['orig_r'], trade['orig_bars'], trade['orig_reason']
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
    if not rs: return {'n':0,'R':0,'wr':0,'pf':0,'exp':0,'mdd':0,'rdd':0,'aw':0,'al':0,'sharpe':0}
    n=len(rs); tr=sum(rs)
    w=[r for r in rs if r>=0.1]; l=[r for r in rs if r<=-0.1]
    gw=sum(w); gl=abs(sum(l))
    pf=gw/gl if gl>0 else 99.9
    eq=0;pk=0;mdd=0
    for r in rs: eq+=r; pk=max(pk,eq); mdd=max(mdd,pk-eq)
    aw=gw/len(w) if w else 0; al=gl/len(l) if l else 0
    mean=tr/n; var=sum((r-mean)**2 for r in rs)/n if n>1 else 0
    std=math.sqrt(var) if var>0 else 0.001
    sharpe=mean/std*math.sqrt(n) if std>0 else 0
    return {'n':n,'R':tr,'wr':len(w)/n*100,'pf':pf,'exp':tr/n,
            'mdd':mdd,'aw':aw,'al':al,'rdd':tr/mdd if mdd>0 else 0,'sharpe':sharpe}

def print_stats(label, s, indent=2):
    sp=' '*indent
    print(f"{sp}{label}: {s['n']}t  WR={s['wr']:.1f}%  PF={s['pf']:.2f}  R={s['R']:+.1f}  "
          f"Exp={s['exp']:+.3f}  MaxDD={s['mdd']:.1f}  R/DD={s['rdd']:.2f}  "
          f"AvgW={s['aw']:.2f}  AvgL={s['al']:.2f}  Sharpe={s['sharpe']:.2f}")

W='='*115; D='-'*115


# ══════════════════════════════════════════════════════════
#  LOAD ALL DATA
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 0: DATA LOADING")
print(W)

all_trades = []
for label, (fname, tp_col, ds) in sorted(FILES.items()):
    fp = os.path.join(UPLOAD_DIR, fname)
    if not os.path.exists(fp):
        print(f"  MISSING: {label} ({fname})")
        continue
    trades = extract_trades(label, fp, tp_col, ds)
    print(f"  {label:>18}: {len(trades):>3} trades  ({ds})")
    all_trades.extend(trades)

all_trades.sort(key=lambda t: t['entry_time'])
print(f"\n  Total raw: {len(all_trades)} BUY trades")

# Apply V2 gates
v2 = apply_v2(all_trades)
print(f"  After V2: {len(v2)} trades")

# Apply stale exit
for t in v2:
    t['final_r'] = final_r(t)

# Split by dataset
dev = [t for t in v2 if t['dataset']=='DEV']
oos_prior = [t for t in v2 if t['dataset']=='OOS_PRIOR']
oos_new = [t for t in v2 if t['dataset']=='OOS_NEW']
oos_all = oos_prior + oos_new

print(f"\n  DEV (in-sample):    {len(dev)} trades")
print(f"  OOS Prior:          {len(oos_prior)} trades")
print(f"  OOS New:            {len(oos_new)} trades")
print(f"  OOS Combined:       {len(oos_all)} trades")


# ══════════════════════════════════════════════════════════
#  SECTION 1: IN-SAMPLE vs OUT-OF-SAMPLE
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 1: IN-SAMPLE vs OUT-OF-SAMPLE — Raw Performance")
print(W)

for label, group in [("DEV (in-sample)", dev), ("OOS Prior", oos_prior),
                      ("OOS New (7 EUR)", oos_new), ("OOS Combined", oos_all), ("ALL DATA", v2)]:
    s_base = stats([t['orig_r'] for t in group])
    s_stale = stats([t['final_r'] for t in group])
    print(f"\n  {label}:")
    print_stats("V2 Baseline", s_base)
    print_stats("V2 + Stale ", s_stale)

# Degradation check — AFTER COSTS (this is what matters)
dev_net = [t['final_r'] - COST_PER_TRADE_R for t in dev]
oos_net = [t['final_r'] - COST_PER_TRADE_R for t in oos_all]
dev_s_net = stats(dev_net)
oos_s_net = stats(oos_net)
print(f"\n  ── OOS Degradation Check (after costs) ──")
print(f"  DEV  Exp={dev_s_net['exp']:+.3f}  WR={dev_s_net['wr']:.1f}%  PF={dev_s_net['pf']:.2f}")
print(f"  OOS  Exp={oos_s_net['exp']:+.3f}  WR={oos_s_net['wr']:.1f}%  PF={oos_s_net['pf']:.2f}")
deg_exp = (dev_s_net['exp']-oos_s_net['exp'])/abs(dev_s_net['exp'])*100 if dev_s_net['exp']!=0 else 0
deg_wr = oos_s_net['wr']-dev_s_net['wr']
deg_pf = oos_s_net['pf']-dev_s_net['pf']
print(f"  Exp degradation: {deg_exp:.1f}%  ({dev_s_net['exp']:+.3f} → {oos_s_net['exp']:+.3f})")
print(f"  WR degradation:  {deg_wr:+.1f}pp")
print(f"  PF degradation:  {deg_pf:+.2f}")
if deg_exp < 50 and oos_s_net['exp'] > 0:
    print(f"  VERDICT: OOS HOLDS — expectancy positive, degradation within normal range")
elif oos_s_net['exp'] > 0:
    print(f"  VERDICT: OOS POSITIVE but significant degradation ({deg_exp:.0f}%) — edge is thinner than dev suggests")
else:
    print(f"  VERDICT: OOS NEGATIVE — strategy may not generalize")


# ══════════════════════════════════════════════════════════
#  SECTION 2: PARAMETER SENSITIVITY (Wobble Test)
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 2: PARAMETER SENSITIVITY — Wobble Test")
print(f"  Tests: does changing parameters ±20% break the strategy?")
print(f"  If yes → overfitted. If no → robust.")
print(W)

params = [
    # (name, [values], apply_func)
    ("ATR %ile Threshold", [50,56,60,66,72,78,84,90],
     lambda v: apply_v2(all_trades, atr_thr=v)),
    ("ADX Threshold",      [12,14,16,18,20,22,24],
     lambda v: apply_v2(all_trades, adx_thr=v)),
    ("Stale Exit Bars",    [5,6,7,8,9,10,12,15],
     None),  # handled separately
    ("Stale MFE Thr",      [0.3,0.4,0.5,0.6,0.7,0.8,1.0],
     None),
]

# ATR and ADX wobble
for name, values, apply_fn in params[:2]:
    print(f"\n  {name} wobble (production value marked *):")
    print(f"  {'Value':>8}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'DD':>5}  {'R/DD':>5}")
    print(f"  {'─'*8}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}")
    for v in values:
        ft = apply_fn(v)
        ft_buy = [t for t in ft if t['dir']=='BUY']
        rs = [final_r(t) for t in ft_buy]
        s = stats(rs)
        prod = " *" if (name=="ATR %ile Threshold" and v==66) or (name=="ADX Threshold" and v==18) else ""
        print(f"  {v:>8}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  "
              f"{s['exp']:>+6.3f}  {s['mdd']:>5.1f}  {s['rdd']:>5.2f}{prod}")

# Stale exit wobble
print(f"\n  Stale Exit parameter wobble:")
print(f"  {'Bars':>5}  {'MFE':>5}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'DD':>5}  {'R/DD':>5}")
print(f"  {'─'*5}  {'─'*5}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*5}")
for sb in [5,6,7,8,9,10,12,15]:
    for sm in [0.3,0.4,0.5,0.6,0.7]:
        rs = [final_r(t, sb, sm) for t in v2]
        s = stats(rs)
        prod = " *" if sb==8 and sm==0.5 else ""
        print(f"  {sb:>5}  {sm:>4.1f}R  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  "
              f"{s['exp']:>+6.3f}  {s['mdd']:>5.1f}  {s['rdd']:>5.2f}{prod}")

# Robustness score
print(f"\n  ── Wobble Summary ──")
base_r = sum(t['final_r'] for t in v2)
wobble_count = 0; profitable_count = 0
for atr_t in [56,60,66,72,78]:
    for adx_t in [14,16,18,20,22]:
        for sb in [6,7,8,9,10]:
            for sm in [0.3,0.4,0.5,0.6,0.7]:
                ft = apply_v2(all_trades, atr_thr=atr_t, adx_thr=adx_t)
                rs = [final_r(t,sb,sm) for t in ft if t['dir']=='BUY']
                wobble_count += 1
                if sum(rs) > 0: profitable_count += 1

pct_profitable = profitable_count/wobble_count*100
print(f"  Tested {wobble_count} parameter combinations (±20% around production)")
print(f"  {profitable_count}/{wobble_count} ({pct_profitable:.1f}%) remain profitable")
if pct_profitable >= 90:
    print(f"  VERDICT: ROBUST — strategy survives parameter perturbation")
elif pct_profitable >= 70:
    print(f"  VERDICT: MODERATELY ROBUST — some parameter sensitivity")
else:
    print(f"  VERDICT: FRAGILE — strategy depends on specific parameter values")


# ══════════════════════════════════════════════════════════
#  SECTION 3: REALISTIC COSTS
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 3: REALISTIC COSTS — Spread + Commission + Slippage")
print(W)

print(f"\n  Cost assumptions:")
print(f"    Realistic: {COST_PER_TRADE_R:.3f}R per trade (1.5 pip spread + $7 comm + 0.5 pip slippage)")
print(f"    Pessimistic: {COST_PESSIMISTIC_R:.3f}R per trade (wider spread broker, worse fills)")

# Average stop distance in pips
avg_stop = sum(t['stop_pips'] for t in v2)/len(v2)
print(f"    Average stop distance: {avg_stop:.0f} pips")

for label, group in [("DEV", dev), ("OOS", oos_all), ("ALL", v2)]:
    rs_gross = [t['final_r'] for t in group]
    rs_real = [t['final_r'] - COST_PER_TRADE_R for t in group]
    rs_pess = [t['final_r'] - COST_PESSIMISTIC_R for t in group]
    sg = stats(rs_gross); sr = stats(rs_real); sp = stats(rs_pess)
    print(f"\n  {label} ({sg['n']} trades):")
    print(f"    Gross:        R={sg['R']:>+6.1f}  Exp={sg['exp']:>+.3f}  PF={sg['pf']:.2f}  R/DD={sg['rdd']:.2f}")
    print(f"    - Realistic:  R={sr['R']:>+6.1f}  Exp={sr['exp']:>+.3f}  PF={sr['pf']:.2f}  R/DD={sr['rdd']:.2f}  (cost: {COST_PER_TRADE_R*sg['n']:.1f}R)")
    print(f"    - Pessimistic:R={sp['R']:>+6.1f}  Exp={sp['exp']:>+.3f}  PF={sp['pf']:.2f}  R/DD={sp['rdd']:.2f}  (cost: {COST_PESSIMISTIC_R*sg['n']:.1f}R)")

# Break-even cost
all_rs = [t['final_r'] for t in v2]
total_r = sum(all_rs)
be_cost = total_r / len(all_rs)
be_cost_pips = be_cost * avg_stop
print(f"\n  Break-even cost: {be_cost:.3f}R ({be_cost_pips:.1f} pips)")
print(f"  The strategy breaks even if round-trip costs exceed {be_cost_pips:.0f} pips per trade")
if be_cost > COST_PESSIMISTIC_R * 1.5:
    print(f"  VERDICT: LARGE COST BUFFER — strategy survives even high-cost brokers")
elif be_cost > COST_PESSIMISTIC_R:
    print(f"  VERDICT: ADEQUATE BUFFER — profitable after realistic costs")
else:
    print(f"  VERDICT: THIN MARGIN — costs eat most of the edge")


# ══════════════════════════════════════════════════════════
#  SECTION 4: BLOCK BOOTSTRAP MONTE CARLO
#  (Corrected: shuffling fixed trades gives trivially 100%
#   profitable because total R doesn't change. Block bootstrap
#   resamples WITH REPLACEMENT in blocks, so total R varies
#   and P(profitable) is a genuine test.)
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 4: BLOCK BOOTSTRAP MONTE CARLO — 10,000 Resampled Sequences")
print(f"  Method: resample N trades WITH REPLACEMENT in blocks of 5")
print(f"  (preserves serial correlation — losing streaks cluster)")
print(f"  Unlike simple shuffle, total R varies per simulation.")
print(W)

N_SIMS = 10000
BLOCK_SIZE = 5
rs_net = [t['final_r'] - COST_PER_TRADE_R for t in v2]
n_trades = len(rs_net)
n_blocks = math.ceil(n_trades / BLOCK_SIZE)

def block_bootstrap(trade_rs, block_size, n_target):
    n = len(trade_rs)
    result = []
    while len(result) < n_target:
        start = random.randint(0, n - 1)
        for j in range(block_size):
            if len(result) >= n_target: break
            result.append(trade_rs[(start + j) % n])
    return result

mc_final_equity = []
mc_max_dd = []
mc_profitable = 0
mc_rdd_positive = 0

for _ in range(N_SIMS):
    resampled = block_bootstrap(rs_net, BLOCK_SIZE, n_trades)
    eq = 0; pk = 0; dd = 0
    for r in resampled:
        eq += r
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    mc_final_equity.append(eq)
    mc_max_dd.append(dd)
    if eq > 0: mc_profitable += 1
    if dd > 0 and eq/dd > 1.0: mc_rdd_positive += 1

mc_final_equity.sort()
mc_max_dd.sort()

print(f"\n  Input: {n_trades} trades (after realistic costs)")
print(f"  Observed total R: {sum(rs_net):+.1f}")

print(f"\n  Resampled Terminal Equity Distribution:")
print(f"    {'Worst simulation':>22}: R = {mc_final_equity[0]:>+6.1f}")
for pct_label, idx in [("1st %ile", int(N_SIMS*0.01)),
                         ("5th %ile", int(N_SIMS*0.05)),
                         ("10th %ile", int(N_SIMS*0.10)),
                         ("25th %ile", int(N_SIMS*0.25)),
                         ("Median", int(N_SIMS*0.50)),
                         ("75th %ile", int(N_SIMS*0.75)),
                         ("95th %ile", int(N_SIMS*0.95))]:
    print(f"    {pct_label:>22}: R = {mc_final_equity[idx]:>+6.1f}")

print(f"\n  Max Drawdown Distribution:")
for pct_label, idx in [("Median DD", int(N_SIMS*0.50)),
                         ("75th %ile DD", int(N_SIMS*0.75)),
                         ("90th %ile DD", int(N_SIMS*0.90)),
                         ("95th %ile DD (plan for this)", int(N_SIMS*0.95)),
                         ("99th %ile DD", int(N_SIMS*0.99))]:
    print(f"    {pct_label:>30}: {mc_max_dd[idx]:.1f}R")

print(f"\n  Key Probabilities:")
print(f"    P(profitable):          {mc_profitable/N_SIMS*100:.1f}%")
print(f"    P(R/DD > 1.0):          {mc_rdd_positive/N_SIMS*100:.1f}%")
p_loss_5r = sum(1 for e in mc_final_equity if e < -5) / N_SIMS * 100
p_gain_20r = sum(1 for e in mc_final_equity if e >= 20) / N_SIMS * 100
print(f"    P(lose > 5R):           {p_loss_5r:.1f}%")
print(f"    P(gain > 20R):          {p_gain_20r:.1f}%")

if mc_profitable/N_SIMS >= 0.95:
    mc_verdict = "HIGH CONFIDENCE"
    print(f"\n  VERDICT: HIGH CONFIDENCE — ≥95% profitable under resampling")
elif mc_profitable/N_SIMS >= 0.80:
    mc_verdict = "GOOD CONFIDENCE"
    print(f"\n  VERDICT: GOOD CONFIDENCE — ≥80% profitable under resampling")
elif mc_profitable/N_SIMS >= 0.60:
    mc_verdict = "MODERATE"
    print(f"\n  VERDICT: MODERATE — profitable in majority but significant ruin risk")
else:
    mc_verdict = "WEAK"
    print(f"\n  VERDICT: WEAK — edge too fragile under resampling")


# ══════════════════════════════════════════════════════════
#  SECTION 5: BLOCK BOOTSTRAP on OOS ONLY (hardest test)
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 5: BLOCK BOOTSTRAP — OOS Data Only (hardest test)")
print(W)

rs_oos_net = [t['final_r'] - COST_PER_TRADE_R for t in oos_all]
n_oos = len(rs_oos_net)

mc_oos_final = []
mc_oos_dd = []
mc_oos_prof = 0

for _ in range(N_SIMS):
    resampled = block_bootstrap(rs_oos_net, BLOCK_SIZE, n_oos)
    eq = 0; pk = 0; dd = 0
    for r in resampled:
        eq += r; pk = max(pk, eq); dd = max(dd, pk - eq)
    mc_oos_final.append(eq)
    mc_oos_dd.append(dd)
    if eq > 0: mc_oos_prof += 1

mc_oos_final.sort()
mc_oos_dd.sort()

print(f"\n  Input: {n_oos} OOS trades (after realistic costs)")
print(f"  Observed OOS R (after costs): {sum(rs_oos_net):+.1f}")

print(f"\n  OOS Resampled Terminal Equity Distribution:")
print(f"    {'Worst simulation':>22}: R = {mc_oos_final[0]:>+6.1f}")
for pct_label, idx in [("1st %ile", int(N_SIMS*0.01)),
                         ("5th %ile", int(N_SIMS*0.05)),
                         ("25th %ile", int(N_SIMS*0.25)),
                         ("Median", int(N_SIMS*0.50)),
                         ("75th %ile", int(N_SIMS*0.75)),
                         ("95th %ile", int(N_SIMS*0.95))]:
    print(f"    {pct_label:>22}: R = {mc_oos_final[idx]:>+6.1f}")

print(f"\n  OOS Max Drawdown Distribution:")
for pct_label, idx in [("Median DD", int(N_SIMS*0.50)),
                         ("95th %ile DD", int(N_SIMS*0.95))]:
    print(f"    {pct_label:>22}: {mc_oos_dd[idx]:.1f}R")

print(f"\n  P(profitable on OOS): {mc_oos_prof/N_SIMS*100:.1f}%")


# ══════════════════════════════════════════════════════════
#  SECTION 5b: BOOTSTRAP CONFIDENCE INTERVAL FOR OOS EXPECTANCY
#  This is the key question: how uncertain is that +0.031R/trade?
# ══════════════════════════════════════════════════════════
print(f"\n  ── Bootstrap 90% Confidence Interval for OOS Expectancy ──")
print(f"  (Resamples OOS trades with replacement, computes mean R/trade)")

boot_exp = []
for _ in range(N_SIMS):
    resampled = block_bootstrap(rs_oos_net, BLOCK_SIZE, n_oos)
    boot_exp.append(sum(resampled) / len(resampled))
boot_exp.sort()

ci_5 = boot_exp[int(N_SIMS * 0.05)]
ci_25 = boot_exp[int(N_SIMS * 0.25)]
ci_50 = boot_exp[int(N_SIMS * 0.50)]
ci_75 = boot_exp[int(N_SIMS * 0.75)]
ci_95 = boot_exp[int(N_SIMS * 0.95)]
p_exp_pos = sum(1 for e in boot_exp if e > 0) / N_SIMS * 100

print(f"    Observed OOS expectancy:  {sum(rs_oos_net)/len(rs_oos_net):+.4f} R/trade")
print(f"    5th percentile:           {ci_5:+.4f} R/trade")
print(f"    25th percentile:          {ci_25:+.4f} R/trade")
print(f"    Median:                   {ci_50:+.4f} R/trade")
print(f"    75th percentile:          {ci_75:+.4f} R/trade")
print(f"    95th percentile:          {ci_95:+.4f} R/trade")
print(f"    90% CI:                   [{ci_5:+.4f}, {ci_95:+.4f}]")
print(f"    Resamples with exp > 0:    {p_exp_pos:.1f}%")
if ci_5 > 0:
    print(f"  INTERPRETATION: Entire 90% CI is positive — strong evidence of positive expectancy")
elif ci_50 > 0:
    print(f"  INTERPRETATION: Median positive but CI includes zero — cannot distinguish from noise")
    print(f"  Zero sits comfortably inside [{ci_5:+.4f}, {ci_95:+.4f}].")
    print(f"  The data are compatible with anything from a modest negative edge to a reasonably positive one.")
else:
    print(f"  INTERPRETATION: Median expectancy is negative or zero — no evidence of edge")

# ── Block size sensitivity ──
print(f"\n  ── Block Size Sensitivity (does block choice change the conclusion?) ──")
for bs in [3, 5, 8, 10, 15]:
    boot_exp_bs = []
    for _ in range(N_SIMS):
        resampled = block_bootstrap(rs_oos_net, bs, n_oos)
        boot_exp_bs.append(sum(resampled) / len(resampled))
    boot_exp_bs.sort()
    bs_ci5 = boot_exp_bs[int(N_SIMS * 0.05)]
    bs_ci95 = boot_exp_bs[int(N_SIMS * 0.95)]
    bs_med = boot_exp_bs[int(N_SIMS * 0.50)]
    bs_ppos = sum(1 for e in boot_exp_bs if e > 0) / N_SIMS * 100
    print(f"    Block={bs:>2}: 90% CI [{bs_ci5:+.4f}, {bs_ci95:+.4f}]  "
          f"Median={bs_med:+.4f}  Resamples>0: {bs_ppos:.1f}%")


# ══════════════════════════════════════════════════════════
#  SECTION 6: YEAR-BY-YEAR BREAKDOWN (approximate)
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 6: TEMPORAL BREAKDOWN — Performance Over Time")
print(W)

# Group by quarter
from collections import OrderedDict
quarters = OrderedDict()
for t in v2:
    q = f"{t['entry_dt'].year} Q{(t['entry_dt'].month-1)//3+1}"
    quarters.setdefault(q, []).append(t)

print(f"\n  {'Quarter':>12}  {'N':>4}  {'WR':>6}  {'PF':>5}  {'R':>7}  {'Exp':>7}  {'DD':>5}  {'Dataset':>10}")
print(f"  {'─'*12}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*10}")
for q, trades in quarters.items():
    rs = [t['final_r'] - COST_PER_TRADE_R for t in trades]
    s = stats(rs)
    ds = trades[0]['dataset']
    flag = " <<<" if s['exp'] < -0.1 else ""
    print(f"  {q:>12}  {s['n']:>4}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  {s['R']:>+6.1f}  {s['exp']:>+6.3f}  "
          f"{s['mdd']:>5.1f}  {ds:>10}{flag}")

# Count losing quarters
losing_q = sum(1 for q, ts in quarters.items() if sum(t['final_r']-COST_PER_TRADE_R for t in ts) < 0)
total_q = len(quarters)
print(f"\n  Losing quarters: {losing_q}/{total_q} ({losing_q/total_q*100:.0f}%)")

# ── Pair × Quarter breakdown ──
print(f"\n  ── Pair × Quarter Breakdown ──")
pair_q = defaultdict(lambda: defaultdict(list))
for t in v2:
    q = f"{t['entry_dt'].year} Q{(t['entry_dt'].month-1)//3+1}"
    pair_q[t['pair']][q].append(t['final_r'] - COST_PER_TRADE_R)

all_pairs_sorted = sorted(set(t['pair'] for t in v2))
all_quarters_sorted = list(quarters.keys())
header = f"  {'Pair':>10}"
for q in all_quarters_sorted:
    header += f"  {q:>10}"
header += f"  {'Total':>8}"
print(header)
print(f"  {'─'*10}" + f"  {'─'*10}" * len(all_quarters_sorted) + f"  {'─'*8}")
for pair in all_pairs_sorted:
    row = f"  {pair:>10}"
    pair_total = 0
    for q in all_quarters_sorted:
        rs = pair_q[pair][q]
        if rs:
            r_sum = sum(rs)
            pair_total += r_sum
            cell = f"{r_sum:+.1f}({len(rs)})"
            row += f"  {cell:>10}"
        else:
            row += f"  {'—':>10}"
    row += f"  {pair_total:>+7.1f}"
    print(row)

# Per-pair totals
print(f"\n  ── Per-Pair Summary (after costs) ──")
print(f"  NOTE: Pair differences are HYPOTHESES for Holdout #2, not established findings.")
print(f"        Multiple-comparisons warning: out of many groups, some will always look good.")
for pair in all_pairs_sorted:
    pair_trades = [t for t in v2 if t['pair'] == pair]
    rs = [t['final_r'] - COST_PER_TRADE_R for t in pair_trades]
    s = stats(rs)
    dev_count = sum(1 for t in pair_trades if t['dataset'] == 'DEV')
    oos_count = sum(1 for t in pair_trades if t['dataset'] != 'DEV')
    print(f"    {pair:>10}: {s['n']:>3}t (DEV:{dev_count} OOS:{oos_count})  "
          f"WR={s['wr']:.0f}%  PF={s['pf']:.2f}  R={s['R']:+.1f}  Exp={s['exp']:+.3f}")


# ══════════════════════════════════════════════════════════
#  SECTION 7: FINAL VERDICT CARD
# ══════════════════════════════════════════════════════════
print(f"\n{W}")
print("  SECTION 7: FINAL VERDICT CARD")
print(W)

# Compile all metrics (reuse the after-cost lists from degradation section)
all_net_final = [t['final_r'] - COST_PER_TRADE_R for t in v2]
s_all = stats(all_net_final); s_dev = stats(dev_net); s_oos = stats(oos_net)

print(f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │               FOREX1998 V3 PRO — STATISTICAL AUDIT             │
  │                    All figures AFTER costs                      │
  ├────────────────────────┬──────────────┬─────────────────────────┤
  │  Metric                │  In-Sample   │  Out-of-Sample          │
  ├────────────────────────┼──────────────┼─────────────────────────┤
  │  Trade Count           │  {s_dev['n']:>8}    │  {s_oos['n']:>8}                 │
  │  Win Rate              │  {s_dev['wr']:>7.1f}%   │  {s_oos['wr']:>7.1f}%                │
  │  Profit Factor         │  {s_dev['pf']:>8.2f}   │  {s_oos['pf']:>8.2f}                │
  │  Expectancy (R/trade)  │  {s_dev['exp']:>+8.3f}   │  {s_oos['exp']:>+8.3f}                │
  │  Total R               │  {s_dev['R']:>+8.1f}   │  {s_oos['R']:>+8.1f}                │
  │  Max Drawdown (R)      │  {s_dev['mdd']:>8.1f}   │  {s_oos['mdd']:>8.1f}                │
  │  R / Max DD            │  {s_dev['rdd']:>8.2f}   │  {s_oos['rdd']:>8.2f}                │
  │  Avg Winner            │  {s_dev['aw']:>+8.2f}   │  {s_oos['aw']:>+8.2f}                │
  │  Avg Loser             │  {s_dev['al']:>8.2f}   │  {s_oos['al']:>8.2f}                │
  │  Sharpe (per-trade)    │  {s_dev['sharpe']:>8.2f}   │  {s_oos['sharpe']:>8.2f}                │
  ├────────────────────────┴──────────────┴─────────────────────────┤
  │  Block Bootstrap Monte Carlo (10K sims, after costs):           │
  │    P(profitable):          {mc_profitable/N_SIMS*100:>5.1f}% (all data, resampled)        │
  │    P(profitable OOS only): {mc_oos_prof/N_SIMS*100:>5.1f}% (resampled)                    │
  │    95th %ile MaxDD:        {mc_max_dd[int(N_SIMS*0.95)]:.1f}R                                │
  │    Worst simulation:       {mc_final_equity[0]:+.1f}R                                   │
  │    1st %ile terminal:      {mc_final_equity[int(N_SIMS*0.01)]:+.1f}R                                   │
  ├────────────────────────────────────────────────────────────────┤
  │  OOS Expectancy 90% Bootstrap CI:                               │
  │    [{ci_5:+.4f}, {ci_95:+.4f}] R/trade                          │
  │    Resamples with exp > 0: {p_exp_pos:>5.1f}%                               │
  ├────────────────────────────────────────────────────────────────┤
  │  Parameter Sensitivity:                                        │
  │    {profitable_count}/{wobble_count} ({pct_profitable:.0f}%) combinations profitable             │
  ├────────────────────────────────────────────────────────────────┤
  │  Cost Resilience:                                              │
  │    Break-even cost: {be_cost:.3f}R ({be_cost_pips:.0f} pips)                       │
  │    Realistic cost:  {COST_PER_TRADE_R:.3f}R → Net R={s_all['R']:+.1f}                    │
  └────────────────────────────────────────────────────────────────┘
""")

# Final classification
checks_passed = 0
checks_total = 6
checks = []

# 1. OOS positive
if s_oos['exp'] > 0:
    checks_passed += 1; checks.append("✓ OOS expectancy positive")
else:
    checks.append("✗ OOS expectancy negative")

# 2. OOS degradation < 50% (after costs)
if deg_exp < 50 and s_oos['exp'] > 0:
    checks_passed += 1; checks.append(f"✓ OOS degradation {deg_exp:.0f}% (< 50%)")
else:
    checks.append(f"✗ OOS degradation {deg_exp:.0f}% (after costs)")

# 3. Block Bootstrap > 80% profitable (genuine resampling test)
if mc_profitable/N_SIMS >= 0.80:
    checks_passed += 1; checks.append(f"✓ Block bootstrap {mc_profitable/N_SIMS*100:.0f}% profitable (resampled)")
else:
    checks.append(f"✗ Block bootstrap only {mc_profitable/N_SIMS*100:.0f}% profitable")

# 4. Parameter robustness > 70%
if pct_profitable >= 70:
    checks_passed += 1; checks.append(f"✓ {pct_profitable:.0f}% of param combos profitable")
else:
    checks.append(f"✗ Only {pct_profitable:.0f}% of param combos profitable")

# 5. Survives realistic costs
if s_all['exp'] > 0:
    checks_passed += 1; checks.append("✓ Profitable after realistic costs")
else:
    checks.append("✗ Not profitable after costs")

# 6. Trade count sufficient (>100)
if s_all['n'] >= 100:
    checks_passed += 1; checks.append(f"✓ Sufficient sample ({s_all['n']} trades)")
else:
    checks.append(f"✗ Small sample ({s_all['n']} trades)")

print(f"  EVIDENCE CHECKLIST ({checks_passed}/{checks_total}):")
for c in checks:
    print(f"    {c}")

print()
if checks_passed == checks_total and ci_5 > 0:
    print(f"  ╔═══════════════════════════════════════════════════════════╗")
    print(f"  ║  CLASSIFICATION: CONFIRMED EDGE                         ║")
    print(f"  ║  OOS expectancy CI entirely positive                    ║")
    print(f"  ╚═══════════════════════════════════════════════════════════╝")
elif checks_passed >= 4 and s_oos['exp'] > 0:
    print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
    print(f"  ║  CLASSIFICATION: CANDIDATE EDGE — REQUIRES INDEPENDENT CONFIRMATION ║")
    print(f"  ║  Positive OOS result consistent with a possible edge, but           ║")
    print(f"  ║  evidence is still weak enough that further testing is required.     ║")
    print(f"  ║  Freeze V3 as-is. Test on Holdout #2 without changing parameters.   ║")
    print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
elif checks_passed >= 2:
    print(f"  ╔═══════════════════════════════════════════════════════════╗")
    print(f"  ║  CLASSIFICATION: INCONCLUSIVE                           ║")
    print(f"  ║  Some positive signals but insufficient evidence        ║")
    print(f"  ╚═══════════════════════════════════════════════════════════╝")
else:
    print(f"  ╔═══════════════════════════════════════════════════════════╗")
    print(f"  ║  CLASSIFICATION: NO EVIDENCE OF EDGE                    ║")
    print(f"  ║  Does not pass minimum statistical thresholds           ║")
    print(f"  ╚═══════════════════════════════════════════════════════════╝")

# Holdout #2 protocol
print(f"\n  ── Holdout #2 Protocol (define BEFORE seeing results) ──")
print(f"")
print(f"  1. Freeze V3 — timestamp/hash the exact rules and parameters")
print(f"  2. Include ALL pairs V3 was originally intended to trade (not just EUR)")
print(f"  3. Ideally 2000+ bars per pair for sufficient sample")
print(f"  4. Write down success criteria BEFORE running:")
print(f"       - 100+ new trades")
print(f"       - Positive after realistic costs (0.054R/trade)")
print(f"       - PF > 1.0")
print(f"       - Expectancy > 0")
print(f"       - No catastrophic concentration in one pair")
print(f"       - Acceptable max drawdown")
print(f"       - Parameter neighborhood remains stable")
print(f"  5. Don't alter anything regardless of what the first few trades show")
print(f"")
print(f"  Preregistered hypothesis (test SEPARATELY):")
print(f"    EUR hypothesis: On completely unseen data, EUR-containing pairs")
print(f"    will have higher expectancy than non-EUR pairs.")
print(f"    (Test this independently — don't use it to change the strategy)")
print(f"")
print(f"  Note: with a true edge of ~+0.031R/trade, narrowing the bootstrap CI")
print(f"  to exclude zero may require 1,500-2,000+ independent-equivalent trades.")
print(f"  A +0.031R edge is hard to distinguish from noise at small samples.")

print(f"\n{W}")
print("  AUDIT COMPLETE")
print(W)
