"""
Backtest: 52-week breakout with trend filters.

Filters (all on signal day's close):
  1. SMA150 > EMA220
  2. Close > SMA50
  3. SMA50  > SMA150
  4. Close > 1.25 * 52-week low
  5. Close was below EMA220 at least once in the past 90 days

Entry:
  - Signal day: close makes a new 52-week high AND all filters pass
  - Buy at NEXT day's open

Exit (whichever comes first):
  - 15% stop-loss: intraday low <= entry * 0.85  -> exit at stop price same day
  - Close < EMA220 on signal day                  -> exit at next day's open

Sizing:
  - Capital ₹50,000, equal-weight ₹5,000/trade (max 10 concurrent positions).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"

INITIAL_CAPITAL = 50_000.0
ALLOC_PER_TRADE = 5_000.0
MAX_POSITIONS = 10
STOP_LOSS_PCT = 0.15
TRADING_DAYS_52W = 252
DIP_LOOKBACK = 90


def load_prices(data_dir: Path) -> dict[str, pd.DataFrame]:
    prices: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(data_dir.glob("*.csv")):
        symbol = csv_path.stem
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[cols].apply(pd.to_numeric, errors="coerce").dropna().sort_index()
        if not df.empty:
            prices[symbol] = df
    return prices


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["Close"]
    out["SMA50"] = c.rolling(50).mean()
    out["SMA150"] = c.rolling(150).mean()
    ema = c.ewm(span=220, adjust=False).mean()
    ema.iloc[:220] = np.nan
    out["EMA220"] = ema
    out["Low52W"] = c.rolling(TRADING_DAYS_52W).min()
    # Prior 52w high — exclude today so a fresh close > prior max is a true breakout
    out["High52W_Prior"] = c.shift(1).rolling(TRADING_DAYS_52W).max()
    below = (c < out["EMA220"]).astype(float)
    out["DipPast90"] = below.rolling(DIP_LOOKBACK).max() > 0
    return out


def signal_mask(df: pd.DataFrame) -> pd.Series:
    f1 = df["SMA150"] > df["EMA220"]
    f2 = df["Close"] > df["SMA50"]
    f3 = df["SMA50"] > df["SMA150"]
    f4 = df["Close"] > 1.25 * df["Low52W"]
    f5 = df["DipPast90"].fillna(False)
    breakout = df["Close"] > df["High52W_Prior"]
    return (f1 & f2 & f3 & f4 & f5 & breakout).fillna(False)


def backtest(prices: dict[str, pd.DataFrame]) -> dict:
    enriched: dict[str, pd.DataFrame] = {}
    for sym, df in prices.items():
        ind = add_indicators(df)
        ind["Signal"] = signal_mask(ind)
        enriched[sym] = ind

    calendar = pd.DatetimeIndex(sorted({d for df in enriched.values() for d in df.index}))

    cash = INITIAL_CAPITAL
    positions: dict[str, dict] = {}
    pending_entries: list[str] = []
    pending_exits: list[str] = []
    trades: list[dict] = []
    equity_curve: list[dict] = []

    def close_position(sym: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(sym)
        proceeds = price * pos["shares"]
        cash += proceeds
        trades.append({
            "symbol": sym,
            "entry_date": pos["entry_date"],
            "entry_price": pos["entry_price"],
            "exit_date": date,
            "exit_price": price,
            "shares": pos["shares"],
            "pnl": (price - pos["entry_price"]) * pos["shares"],
            "return_pct": (price / pos["entry_price"] - 1) * 100,
            "holding_days": (pd.Timestamp(date) - pd.Timestamp(pos["entry_date"])).days,
            "exit_reason": reason,
        })

    for date in calendar:
        # 1. EMA-exits at today's open (queued from prior close)
        for sym in pending_exits:
            if sym not in positions:
                continue
            df = enriched[sym]
            if date in df.index:
                close_position(sym, date, float(df.loc[date, "Open"]), "EMA220")
        pending_exits = []

        # 2. New entries at today's open (queued from prior close), deterministic order
        for sym in sorted(pending_entries):
            if sym in positions or len(positions) >= MAX_POSITIONS:
                continue
            df = enriched[sym]
            if date not in df.index:
                continue
            open_px = float(df.loc[date, "Open"])
            if not np.isfinite(open_px) or open_px <= 0:
                continue
            alloc = min(ALLOC_PER_TRADE, cash)
            shares = int(alloc // open_px)
            cost = shares * open_px
            if shares <= 0 or cost > cash:
                continue
            cash -= cost
            positions[sym] = {
                "entry_date": date,
                "entry_price": open_px,
                "shares": shares,
                "stop_price": open_px * (1 - STOP_LOSS_PCT),
            }
        pending_entries = []

        # 3. Intraday stop-loss check on open positions
        for sym in list(positions):
            df = enriched[sym]
            if date not in df.index:
                continue
            low = float(df.loc[date, "Low"])
            stop = positions[sym]["stop_price"]
            if low <= stop:
                close_position(sym, date, stop, "StopLoss")

        # 4. End-of-day: queue tomorrow's actions from today's close
        for sym, df in enriched.items():
            if date not in df.index:
                continue
            row = df.loc[date]
            if sym in positions:
                ema = row["EMA220"]
                if pd.notna(ema) and row["Close"] < ema:
                    pending_exits.append(sym)
            else:
                if bool(row["Signal"]):
                    pending_entries.append(sym)

        # 5. Mark-to-market
        mv = 0.0
        for sym, pos in positions.items():
            df = enriched[sym]
            px = float(df.loc[date, "Close"]) if date in df.index else pos["entry_price"]
            mv += px * pos["shares"]
        equity_curve.append({"date": date, "cash": cash, "market_value": mv,
                             "equity": cash + mv, "open_positions": len(positions)})

    # Close any still-open positions at last available close (informational)
    last = calendar[-1]
    for sym in list(positions):
        df = enriched[sym]
        if last in df.index:
            close_position(sym, last, float(df.loc[last, "Close"]), "OpenAtEnd")

    return {
        "trades": pd.DataFrame(trades),
        "equity": pd.DataFrame(equity_curve).set_index("date"),
    }


def report(result: dict) -> None:
    trades, equity = result["trades"], result["equity"]
    print(f"\n{'=' * 60}\nBACKTEST RESULTS\n{'=' * 60}")
    if equity.empty:
        print("No equity data.")
        return

    final = float(equity["equity"].iloc[-1])
    total_ret = (final / INITIAL_CAPITAL - 1) * 100

    peak = equity["equity"].cummax()
    dd_pct = ((equity["equity"] - peak) / peak * 100).min()

    daily_ret = equity["equity"].pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() else 0.0

    n = len(trades)
    if n:
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] <= 0]
        win_rate = len(wins) / n * 100
        avg_w = wins["return_pct"].mean() if len(wins) else 0.0
        avg_l = losses["return_pct"].mean() if len(losses) else 0.0
        gross_w = wins["pnl"].sum()
        gross_l = losses["pnl"].sum()
        pf = abs(gross_w / gross_l) if gross_l else float("inf")
        avg_hold = trades["holding_days"].mean()
    else:
        win_rate = avg_w = avg_l = pf = avg_hold = 0.0

    print(f"Period:           {equity.index[0].date()} -> {equity.index[-1].date()}")
    print(f"Initial Capital:  ₹{INITIAL_CAPITAL:,.2f}")
    print(f"Final Equity:     ₹{final:,.2f}")
    print(f"Total Return:     {total_ret:+.2f}%")
    print(f"Max Drawdown:     {dd_pct:.2f}%")
    print(f"Sharpe (annual):  {sharpe:.2f}")
    print(f"\nTrades:           {n}")
    print(f"Win Rate:         {win_rate:.1f}%")
    print(f"Avg Win:          {avg_w:+.2f}%")
    print(f"Avg Loss:         {avg_l:+.2f}%")
    print(f"Profit Factor:    {pf:.2f}")
    print(f"Avg Holding Days: {avg_hold:.1f}")
    if n:
        print("\nExits by reason:")
        print(trades["exit_reason"].value_counts().to_string())

    RESULTS_DIR.mkdir(exist_ok=True)
    trades.to_csv(RESULTS_DIR / "trades.csv", index=False)
    equity.to_csv(RESULTS_DIR / "equity_curve.csv")
    print(f"\nSaved -> {RESULTS_DIR/'trades.csv'}")
    print(f"Saved -> {RESULTS_DIR/'equity_curve.csv'}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=str(DATA_DIR))
    args = p.parse_args()

    prices = load_prices(Path(args.data_dir))
    print(f"Loaded {len(prices)} symbols from {args.data_dir}")
    if not prices:
        print("No data found. Run download_data.py first.")
        return

    result = backtest(prices)
    report(result)


if __name__ == "__main__":
    main()
