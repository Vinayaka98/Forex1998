#!/usr/bin/env python3
"""
CSV Format Validator for Holdout #2 Data
========================================
Checks that exported TradingView CSVs have the columns the analysis scripts need.

Usage:
  python validate_csv.py /path/to/csv1.csv [csv2.csv ...]
  python validate_csv.py --dir /path/to/data/

TradingView Export Steps (4H chart, per pair):
  1. Apply "Forex1998 Blueprint V3 Pro Order Indicator" to the chart
  2. Set timeframe to 4H
  3. Ensure the indicator's SL/TP lines are visible (Show Stop/Target Lines = ON)
  4. Select the date range for Holdout #2
  5. Export chart data: three-dot menu → Export chart data
  6. The CSV should contain at minimum: time, open, high, low, close, Active SL, Active TP2
"""
import csv, sys, os, argparse

REQUIRED = {"time", "open", "high", "low", "close"}
SIGNAL_COLS = {"Active SL"}
TP_OPTIONS = ["Active TP2", "Active TP", "Active TP1"]

def validate(filepath):
    issues = []
    try:
        with open(filepath) as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            if not headers:
                return [f"  EMPTY: no headers found"]

            missing_req = REQUIRED - headers
            if missing_req:
                issues.append(f"  MISSING required columns: {', '.join(sorted(missing_req))}")

            if not SIGNAL_COLS & headers:
                issues.append(f"  MISSING signal column: 'Active SL' — indicator not applied or SL/TP lines hidden")

            has_tp = any(tp in headers for tp in TP_OPTIONS)
            if not has_tp:
                issues.append(f"  MISSING target column: none of {TP_OPTIONS} found")

            rows = list(reader)
            n = len(rows)
            if n == 0:
                issues.append(f"  EMPTY: no data rows")
                return issues

            sl_count = sum(1 for r in rows if r.get('Active SL', '').strip())
            tp_col = next((c for c in TP_OPTIONS if c in headers), None)
            tp_count = sum(1 for r in rows if tp_col and r.get(tp_col, '').strip()) if tp_col else 0

            extra_cols = headers - REQUIRED - SIGNAL_COLS - set(TP_OPTIONS)
            hma_cols = [c for c in extra_cols if 'HMA' in c.upper()]

            if not issues:
                issues.append(f"  OK: {n} bars, {sl_count} bars with SL, {tp_count} bars with TP")
                if sl_count == 0:
                    issues.append(f"  WARNING: Active SL column exists but all values empty — no trades in this period?")
            else:
                present = sorted(headers)
                issues.append(f"  HAS columns: {', '.join(present)}")
                issues.append(f"  ROWS: {n}")
                if hma_cols:
                    issues.append(f"  NOTE: HMA columns present — this looks like raw chart data without the V3 indicator")

    except Exception as e:
        issues.append(f"  ERROR reading file: {e}")
    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate CSV format for Holdout #2 analysis")
    parser.add_argument("files", nargs="*", help="CSV files to validate")
    parser.add_argument("--dir", help="Directory containing CSV files")
    args = parser.parse_args()

    files = list(args.files)
    if args.dir:
        files.extend(
            os.path.join(args.dir, f)
            for f in sorted(os.listdir(args.dir))
            if f.endswith('.csv')
        )
    if not files:
        print("No CSV files specified. Use: validate_csv.py file.csv [...]  or  --dir /path/")
        sys.exit(1)

    all_ok = True
    print(f"Validating {len(files)} CSV file(s)...\n")
    for fp in files:
        name = os.path.basename(fp)
        print(f"{name}:")
        results = validate(fp)
        for r in results:
            print(r)
            if "MISSING" in r or "ERROR" in r:
                all_ok = False
        print()

    if all_ok:
        print("All files passed validation.")
    else:
        print("=" * 60)
        print("SOME FILES NEED RE-EXPORT FROM TRADINGVIEW")
        print("=" * 60)
        print()
        print("To export correctly:")
        print("  1. Open the pair's chart in TradingView (4H timeframe)")
        print("  2. Add the 'Forex1998 Blueprint V3 Pro Order Indicator'")
        print("  3. In indicator settings: Show Stop/Target Lines = ON")
        print("  4. Menu (three dots) → Export chart data")
        print("  5. The CSV must contain 'Active SL' and 'Active TP2' columns")
        print()
        print("The analysis scripts detect trades from the indicator's own")
        print("Active SL/TP output. Raw OHLC data alone is not sufficient")
        print("because the indicator uses Volume Profile, multi-timeframe")
        print("analysis, and 20+ sub-indicators to generate signals.")


if __name__ == "__main__":
    main()
