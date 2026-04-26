import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_SYMBOLS_CSV = "./NASDAQ100.csv"
DEFAULT_DATA_DIR = Path(__file__).parent / "data"
DEFAULT_START = "2025-01-01"


def load_symbols(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    symbols = df["Symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    return symbols


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
    parser = argparse.ArgumentParser(description="Download NASDAQ 100 daily data from Yahoo Finance")
    parser.add_argument("--symbols-csv", default=DEFAULT_SYMBOLS_CSV, help="Path to CSV with a 'Symbol' column")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD), default: today")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Output directory for CSVs")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between requests")
    args = parser.parse_args()

    out_dir = Path(args.data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = load_symbols(args.symbols_csv)
    print(f"Loaded {len(symbols)} symbols from {args.symbols_csv}")
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
