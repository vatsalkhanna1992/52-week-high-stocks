# Buy/Sell Strategy App

End-to-end Python toolkit to **download** index constituent daily data from Yahoo Finance, **backtest** a 52-week breakout strategy with trend filters, and **scan live** via a Streamlit dashboard.

Supports multiple universes — currently **NASDAQ 100** (US, USD) and **Nifty 50** (India, INR). Add more by extending `universe.py`.

---

## 📁 Project layout

```
buy_sell_strategy_app/
├── NASDAQ100.csv          # NASDAQ 100 symbol list
├── Nifty50.csv            # Nifty 50 symbol list (Yahoo .NS suffix)
├── universe.py            # universe registry + symbol loader
├── download_data.py       # fetches daily OHLCV → data/<universe>/<SYMBOL>.csv
├── backtest.py            # runs the strategy backtest per universe
├── dashboard.py           # Streamlit live scanner (universe picker)
├── requirements.txt
├── data/
│   ├── nasdaq100/         # per-symbol CSVs
│   └── nifty50/
└── results/
    ├── nasdaq100/         # trades.csv, equity_curve.csv
    └── nifty50/
```

---

## ⚙️ Installation

```bash
pip install -r requirements.txt
```

Dependencies: `pandas`, `numpy`, `yfinance`, `streamlit`.

---

## 1. Download data — `download_data.py`

Reads symbols from the universe CSV and saves one CSV per ticker into `data/<universe>/`.

```bash
# NASDAQ 100 (default)
python download_data.py --start 2023-01-01

# Nifty 50
python download_data.py --universe nifty50 --start 2023-01-01

# overrides if you want a custom CSV / output dir
python download_data.py --universe nifty50 --symbols-csv ./Nifty50.csv --data-dir ./data/nifty50
```

> **Recommendation:** for the backtest to produce meaningful signals, download at least one extra year of history so 220-day EMA and 52-week stats have full lookback. Use `--start 2023-01-01` or earlier.

---

## 2. Backtest — `backtest.py`

```bash
python backtest.py                       # NASDAQ 100 (default)
python backtest.py --universe nifty50    # Nifty 50
```

Outputs (per universe):
- Console summary (returns, drawdown, Sharpe, win rate, profit factor, exit-reason counts) — formatted with the universe's currency symbol
- `results/<universe>/trades.csv` — every trade with entry/exit prices, PnL, holding days, exit reason
- `results/<universe>/equity_curve.csv` — daily cash, market value, equity, open positions

### Strategy rules

**Filters (all on signal day's close):**
| # | Condition |
|---|---|
| F1 | `SMA150 > EMA220` |
| F2 | `Close > SMA50` |
| F3 | `SMA50 > SMA150` |
| F4 | `Close > 1.25 × 52-week Low` (≥ 25% off the low) |
| F5 | `Close < EMA220` at least once in the past 90 days |

**Entry:** F1–F5 all true **and** today's close makes a new 52-week high (close > prior 252-day max). Buy at the **next day's open**.

**Exit (whichever first):**
- **15% stop-loss** — intraday `Low ≤ entry × 0.85` ⇒ exit at stop price same day
- **EMA exit** — `Close < EMA220` ⇒ exit at next day's open

**Sizing:** ₹50,000 starting capital, ₹5,000 (10%) per trade, max 10 concurrent positions, integer share counts.

---

## 3. Live dashboard — `dashboard.py`

```bash
streamlit run dashboard.py
```

Pick the **universe** from the sidebar (NASDAQ 100 / Nifty 50). Pulls fresh data via `yfinance` (batched, 5-minute cache) and displays:

- 🕒 **Last-refresh timestamp** with relative age
- 🚀 **Buy Signals** — symbols satisfying all filters AND breaking out today
- 👀 **Watchlist** — all 5 filters pass, waiting for breakout
- 📊 **All Symbols** — sortable summary
- 🔍 **Detail** — per-symbol filter checklist (✅/❌) and a price/SMA/EMA chart

Sidebar controls: universe picker, lookback days, force-refresh button, filter legend.

### Adding a new universe

Edit `universe.py` and add an entry to `UNIVERSES`:

```python
"sp500": {
    "label": "S&P 500",
    "csv": ROOT / "SP500.csv",
    "data_dir": ROOT / "data" / "sp500",
    "results_dir": ROOT / "results" / "sp500",
    "currency": "$",
},
```

Drop a `SP500.csv` (column `Symbol`) in the project root — it auto-appears in the dashboard and CLI choices.

The dashboard imports `add_indicators` and `signal_mask` directly from `backtest.py`, so live signals always match backtest logic.

---

## 🛠 Conventions

- **Signals on close, fills at next open** (entries and EMA exits).
- **Indicators use `min_periods = window`** — early rows return NaN until enough data exists.
- **Breakout** uses the *prior* 252-day max (today excluded) so a fresh new high is genuine.
- All files use unadjusted OHLC from Yahoo Finance (`auto_adjust=False`).

---

## ⚠️ Disclaimer

This code is for educational and research purposes only. It is not investment advice. Past performance is not indicative of future results.
