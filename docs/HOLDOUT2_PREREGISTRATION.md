# Holdout #2 Preregistration Protocol
## Forex1998 Blueprint V3 Pro — Independent Confirmation Test

**Date locked:** 2026-09-20
**Status:** PREREGISTERED — DO NOT MODIFY AFTER DATA COLLECTION BEGINS

---

## 1. Frozen Strategy

- **Version:** V3 + V2 filters + Stale Exit
- **Git commit (strategy):** `24b2f02` (Add stale exit management)
- **Frozen branch:** `frozen/v3-pre-holdout2` (points at the final immutable commit)
- **Pine Script SHA-256:** `09150ace06cd9cf8e54f21c84197b8a2dc6cc5196220761734829d99f93a14bc`
- **File:** `Forex1998_Order_Indicator.pine` (frozen copy: `strategy/v3_frozen.pine`)
- **No strategy changes permitted** until this holdout is fully analyzed

### V3 Parameters (frozen)
- ADX threshold: 18.0
- ATR percentile threshold: 66
- ATR percentile lookback: 100
- Stale exit: bar >= 8 AND max MFE < 0.5R
- Direction: BUY only (long-EUR system)
- Timeframe: 4H

---

## 2. Pairs to Test

**ALL original V3 pairs must be included.** This is not optional — testing only EUR pairs would be optimizing on prior OOS results.

### Required pairs:
| Group | Pairs |
|-------|-------|
| DEV EUR (5) | EURUSD, EURCAD, EURAUD, EURGBP, EURNZD |
| Prior OOS EUR (1) | EURCHF |
| Prior OOS non-EUR (5) | USDCAD, NZDUSD, AUDUSD, USDJPY, GBPUSD* |
| New OOS EUR (1) | EURJPY |

*Include any additional pairs that V3 was previously tested on.

### Broker:
- Use OANDA feed for consistency with DEV data
- If using a different broker, document it and note any spread differences

---

## 3. Data Requirements & Stopping Rule

### Stopping rule (predefined — no discretion):
> Run the predefined calendar period. If fewer than 300 eligible trades are
> generated, extend by exactly six calendar months and rerun. Continue in
> six-month increments until the dataset contains at least 300 eligible trades.
> Include every eligible trade in the final six-month block; do not stop when
> trade #300 occurs.

**Do NOT use a trade-count target with discretion to stop anywhere in a range.** The endpoint is always the end of a calendar block, never an individual trade arrival.

### Data specifications:
- **Calendar period:** Select a contiguous date range BEFORE viewing any results
- **Time period:** Must be different from all existing data (DEV and prior OOS)
- Export with Active SL and Active TP columns visible in TradingView
- Every trade generated in the selected period is included — no exceptions

### Note on statistical power:
300 trades may remain statistically inconclusive at +0.031R/trade expectancy. That's acceptable — Holdout #2's job is replication, not producing a predetermined verdict.

---

## 4. Cost Model (locked)

### Per-trade cost calculation (not a flat constant):
Costs vary by pair and stop distance. Each trade's cost is computed individually:

```
cost_pips = spread_pips + commission_pips + slippage_pips
cost_R    = cost_pips / stop_distance_pips
```

This is critical: a 30-pip stop pays ~0.08R in costs, while a 70-pip stop pays ~0.035R. A flat 0.054R understates costs on tight stops and overstates them on wide stops.

### Component assumptions:

| Component | Realistic | Pessimistic | Source |
|-----------|-----------|-------------|--------|
| Spread | Per-pair typical (see below) | +1.0 pip | OANDA typical spreads |
| Commission | $7/100k RT (~0.7 pips) | $10/100k RT (~1.0 pips) | Broker schedule |
| Slippage | 0.5 pips | 1.0 pips | Conservative estimate |

### Pair-specific typical spreads (realistic scenario):
| Pair | Typical Spread (pips) |
|------|----------------------|
| EURUSD | 1.0 |
| EURGBP | 1.5 |
| EURAUD | 2.0 |
| EURCAD | 2.0 |
| EURNZD | 2.5 |
| EURCHF | 2.0 |
| EURJPY | 1.5 |
| USDCAD | 1.5 |
| NZDUSD | 1.5 |
| AUDUSD | 1.0 |
| USDJPY | 1.0 |
| GBPUSD | 1.5 |

### Reference: at 50-pip average stop
| Scenario | Approx total cost (pips) | Approx R |
|----------|-------------------------|----------|
| Realistic (EUR major) | 2.2 pips | ~0.044R |
| Realistic (EUR cross) | 3.2 pips | ~0.064R |
| Pessimistic (EUR major) | 3.5 pips | ~0.070R |
| Pessimistic (EUR cross) | 4.5 pips | ~0.090R |

---

## 5. Analysis Protocol

### Step 1: Analyze Holdout #2 BY ITSELF first
- Do NOT combine with existing OOS data initially
- This is the clean, independent test
- Report all metrics below on Holdout #2 data alone

### Step 2: Then combine for estimation (optional, secondary)
- After Holdout #2 standalone analysis is complete, may combine all OOS data for tighter estimation
- Label combined analysis clearly as "Combined estimation" not "new OOS evidence"

### Metrics to report:
- Trade count (total, per pair)
- Win rate
- After-cost expectancy (R/trade) — **PRIMARY METRIC**
- Profit factor
- Net R (total)
- Max drawdown (R)
- 90% Bootstrap confidence interval for expectancy
- Block bootstrap: sizes 3, 5, 8, 10, 15

### No filtering or removal of trades after the fact
- Every trade V3 generates on the selected data is included
- No cherry-picking pairs, time windows, or individual trades

---

## 6. Preregistered Hypotheses

### Primary hypothesis (whole-system test):
> V3's after-cost expectancy on Holdout #2 data (all pairs) is positive.

### Secondary hypothesis (EUR-specific, tested separately):
> V3's after-cost expectancy on EUR pairs in Holdout #2 is higher than on non-EUR pairs.

**These are the only two hypotheses.** Any other patterns discovered are exploratory findings, not confirmations.

### Preregistered validation method: Temporal clustering bootstrap
Multiple FX pairs can trigger on the same macro move (e.g., ECB announcement fires EURUSD + EURGBP + EURNZD simultaneously). These are not three independent trades — they share the same driver.

To account for this:
> Bootstrap/cluster trades by calendar day or overlapping exposure windows. Trades open on the same calendar day across any pairs are treated as a single cluster. Resample clusters (not individual trades) to compute the confidence interval.

This prevents correlated trades from inflating the effective sample size. Report both:
1. Standard block bootstrap CI (individual trades, as in V3 audit)
2. Cluster bootstrap CI (calendar-day clusters)

The cluster CI is the more conservative and more honest measure.

---

## 7. Interpretation Framework (defined BEFORE seeing results)

### Strong confirmation:
- Positive after-cost expectancy
- 90% CI materially tighter and preferably entirely above zero
- No single pair responsible for most of the profit
- Both realistic and pessimistic cost scenarios remain profitable

### Promising but inconclusive:
- Positive expectancy but CI still crosses zero
- Or: profitable overall but one pair dominates

### No confirmation:
- Expectancy around zero or negative
- Results collapse after realistic execution costs
- Or: only profitable under optimistic cost assumptions

---

## 8. What Happens After

- **Strong confirmation →** V3 can be traded live with proper position sizing. Consider paper trading first.
- **Promising but inconclusive →** Need more data. Do NOT modify strategy parameters. Consider Holdout #3.
- **No confirmation →** The edge is not real or not tradeable. Strategy needs fundamental rethink, not parameter tweaking.

**In NO case should V3 parameters be adjusted based on Holdout #2 results.** That would convert confirmation data into optimization data, invalidating the test.

---

## 9. Prior Results Summary (for reference only)

| Dataset | Trades | Expectancy (gross) | Expectancy (after cost) |
|---------|--------|--------------------|------------------------|
| DEV (in-sample) | 185 | +0.207R | +0.153R |
| OOS (all prior) | 109 | +0.085R | +0.031R |
| **Degradation** | | | **79.7%** |

- OOS 90% Bootstrap CI: [-0.091, +0.154]
- ~65-69% of bootstrap resamples positive (stable across block sizes)
- 625/625 parameter combinations profitable (robustness evidence, not proof)
- Classification: **CANDIDATE EDGE — REQUIRES INDEPENDENT CONFIRMATION**

---

*This document was locked before Holdout #2 data collection began. Any modifications after data collection starts invalidate the preregistration.*
