# Forex1998

## Level Trader 15m / 4H / D (TradingView, Pine Script v6)

`indicators/level_trader.pine` automates the *NY session checklist v4*
with every kill switch applied, and fires an alert with
**market BUY/SELL, entry, stop, target, BE / 2R levels and lot size**.
It reads the chart's timeframe and runs the same checklist one level up or down:

| Chart | Bias | Zones (swings, range) | Volume profile | VWAP | Entry window | Pip settings |
|---|---|---|---|---|---|---|
| 15m | Daily HMA 200 | 4H | prev week + prev month; session POC as confluence | session, used | 9:30–12:00 NY | as entered |
| 4H | 4H HMA 200 | 4H | prev week | not used | any 4H close | × 4 |
| Daily | Daily HMA 200 | Daily | prev month | not used | daily close | × 10 |

HMA 55 on the chart is the momentum flag on every stack. This matches the indicators on your charts;
VRVP and Gaps are not used (VRVP depends on the visible screen, Gaps is not in the checklist).

The 4H and Daily stacks are the **same rules scaled up, not a separately designed strategy**.
Nothing in the PDF was written for them, so treat them as untested until the model results say otherwise.
News blackout only works on the 15m stack; on 4H/D check the calendar yourself.
4H and Daily trades are held overnight and often over weekends — check that your prop-firm account type allows it.

### Install
1. TradingView → Pine Editor → paste the file → *Add to chart*.
2. Use a **15m, 4H or Daily** chart of EURUSD, GBPUSD, USDJPY or USDCAD. Alerts are prefixed `[15m]`, `[4H]` or `[D]`.
3. Settings → *Position size*: set account size and account currency (default 120000 CAD, 0.25%).

### Alerts (one-time setup, once per pair and timeframe)
Pine scripts cannot create alerts themselves. On each pair's chart:
*Create alert* → Condition: **NY Session Level Trader** → **Any alert() function call** → Trigger: *Once per bar close*.
That single alert carries entry signals, 1R/2R/stop/target management messages, and (optional) level-reached heads-ups.

### How the checklist is translated into rules (15m stack; higher stacks swap timeframes per the table above)

| Checklist item | What the code does |
|---|---|
| Daily bias / trend vs range | Trend LONG if yesterday's close > Daily HMA 200, > close 15 days ago, and the last 10 closes all above the HMA (mirror for SHORT). Otherwise RANGE. Can be overridden manually. |
| Monthly / Weekly PVP | POC/VAH/VAL of the **previous** month/week, computed from the chart's tick volume (70% value area). |
| 4H swings (max 4–6) | 4H pivots (5 bars each side) with ≥30-pip reversal, last 21 days, max 3 highs + 3 lows. |
| Confluence | Number of levels within 8 pips. ≥2 = strong level. |
| Range edges | Highest high / lowest low of the last 30 completed 4H bars. |
| VWAP traffic light | Session VWAP 8-bar slope. Trend: must agree, or level must be strong. Range: flat/agree, or strong level. |
| ATR ≥ 4 pips | 15m ATR(14) in pips. |
| HMA 55 | Not a filter; flagged as "consider 1.5R exit" when not with you. |
| Patterns | WICK (≥50% wick past level, body on your side), ENGULF, 2xTAP (two touches, pulled away in between, never closed through), B&R (trend only). Candle close only. |
| Stop | Beyond rejection wick (trend) or range edge (range) + 2.5 pips. Must be 0.5–1.5× ATR; outside that the trade is skipped (wick dictates, ATR validates). "Widen to min" is available in settings for testing. |
| Target | Trend: next level beyond entry (outside the entry level's cluster). Range: 75% toward opposite edge. Must be ≥ 2R. |
| Kill switches | Shorting into support / buying into resistance (room < 2R), chasing (3-bar move > 2.5× ATR), oversized candle (> 2× ATR), missed (>15 pips from level), ATR < 4, no man's land (no target level), range middle/narrow (< 3× ATR or < 3× stop), 3rd+ retest of a range edge, outside 9:30–12:00 ET, news blackout, chop. |
| Chop | ≥4 colour flips in the last 6 candles, or 3 flips plus ≥2 indecision candles (body < 35% of range, or 25%+ wicks on both sides). |
| Adding trades | A new signal is allowed while trades are open only if every open trade is risk-free (default: 50% taken at 2R, option: stop at breakeven), the new level is not the same level, and fewer than 3 trades are open. Total live risk therefore never exceeds 0.25%. Blocked setups show the reason, including this one. |
| Trade management | BE at 1R. Trend: 50% off at 2R, runner trails behind each new confirmed 15m swing + buffer (alert on every move), or exits at the target in *Fixed target* mode. Range: all at target. |

Blocked setups are marked with a grey × — hover to see which kill switch stopped it.

### Known gaps (read before trusting it)
- **VRVP** depends on what is on your screen; it is not reproducible in code and is replaced by the weekly/monthly profiles.
- **News**: Pine cannot read forexfactory. Type the day's red-flag times into the input; they apply to every day on the chart.
- **Profiles use tick volume** with fixed rows, so levels will differ by a few pips from TradingView's own PVP drawing.
- **Model results** in the table follow the trade-management rules above, assuming the stop is hit first when a candle hits both. Every trade is charged *Spread + commission* (default 1.0 pip), and setups where that cost exceeds 20% of the stop are blocked. No slippage. Flip *Runner exit* between trail and fixed target to compare them. Treat it as a sanity check, not a backtest.
- **Lot size** converts the quote currency to your account currency (`request.currency_rate`). The PDF calculator's example (EURUSD, 6 pips, 300 CAD → 5.00 lots) assumes $10/pip in CAD and over-sizes EURUSD/GBPUSD trades by the USD/CAD rate (~35–40%).
