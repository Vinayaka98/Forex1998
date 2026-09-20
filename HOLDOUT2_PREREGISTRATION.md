# Holdout #2 Preregistration Protocol
## Forex1998 Blueprint V3 Pro — Independent Confirmation Test

**Date locked:** 2026-09-20
**Status:** PREREGISTERED — DO NOT MODIFY AFTER DATA COLLECTION BEGINS

---

## 1. Frozen Strategy

- **Version:** V3 + V2 filters + Stale Exit
- **Git commit:** `24b2f02` (Add stale exit management)
- **Pine Script SHA-256:** `09150ace06cd9cf8e54f21c84197b8a2dc6cc5196220761734829d99f93a14bc`
- **File:** `Forex1998_Order_Indicator.pine`
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

## 3. Data Requirements

- **Target: at least 200-300 genuinely untouched trades** (not bars — trades are what matter statistically)
- Bars are raw history; trade count depends on signal frequency
- At current signal frequency (~1 trade per 25-50 bars per pair), aim for **5,000-10,000+ bars per pair** to generate enough trades
- **Time period:** Must be different from all existing data (DEV and prior OOS)
- **Date range must be selected BEFORE viewing any performance results**
- Export with Active SL and Active TP columns visible in TradingView

---

## 4. Cost Assumptions (locked)

| Component | Realistic | Pessimistic |
|-----------|-----------|-------------|
| Spread | 1.5 pips (0.030R) | 2.5 pips (0.050R) |
| Commission | $7/100k RT (0.014R) | $10/100k RT (0.020R) |
| Slippage | 0.5 pips (0.010R) | 1.0 pips (0.020R) |
| **Total** | **0.054R/trade** | **0.080R/trade** |

Based on ~50 pip average stop distance on 4H EUR pairs.

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
