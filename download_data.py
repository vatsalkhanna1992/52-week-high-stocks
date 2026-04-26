import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

import universe as uni

DEFAULT_UNIVERSE = "nasdaq100"
DEFAULT_START = "2025-01-01"


def download_symbol(symbol: str, start: str, end: str | None, out_dir: Path) -> bool:
    try:
        df = yf.download(
            symbol,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        print(f"  [ERROR] {symbol}: {exc}")
        return False

    if df is None or df.empty:
        print(f"  [SKIP]  {symbol}: no data returned")
        return False

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.index.name = "Date"
    out_path = out_dir / f"{symbol}.csv"
    df.to_csv(out_path)
    print(f"  [OK]    {symbol}: {len(df)} rows -> {out_path.name}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download daily OHLCV from Yahoo Finance for a universe")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE, choices=list(uni.UNIVERSES),
                        help="Universe key (default: nasdaq100)")
    parser.add_argument("--symbols-csv", default=None,
                        help="Override path to symbols CSV (default: from universe)")
    parser.add_argument("--data-dir", default=None,
                        help="Override output dir (default: from universe)")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD), default: today")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between requests")
    args = parser.parse_args()

    cfg = uni.get(args.universe)
    csv_path = args.symbols_csv or cfg["csv"]
    out_dir = Path(args.data_dir) if args.data_dir else cfg["data_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = uni.load_symbols(csv_path)
    print(f"Universe: {cfg['label']}  ({len(symbols)} symbols from {csv_path})")
    print(f"Saving to {out_dir} (start={args.start}, end={args.end or 'today'})\n")

    ok, fail = 0, 0
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}")
        if download_symbol(symbol, args.start, args.end, out_dir):
            ok += 1
        else:
            fail += 1
        if args.sleep:
            time.sleep(args.sleep)

    print(f"\nDone. Success: {ok}, Failed: {fail}")


if __name__ == "__main__":
    main()
