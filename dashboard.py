"""
Live scanner: pulls Yahoo Finance daily data for NASDAQ 100 and shows
which stocks satisfy the strategy filters / breakout signal right now.

Run:
    streamlit run dashboard.py
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import yfinance as yf

from backtest import add_indicators, signal_mask
from download_data import download_symbol
import universe as uni

ROOT = Path(__file__).parent

FILTER_LABELS = {
    "F1": "SMA150 > EMA220",
    "F2": "Close > SMA50",
    "F3": "SMA50 > SMA150",
    "F4": "Close > 1.25 × 52W Low",
    "F5": "Dipped EMA220 in past 90d",
    "BO": "Breakout (new 52W high)",
}


@st.cache_data(ttl=300, show_spinner=False)
def load_symbols(path: str) -> list[str]:
    return uni.load_symbols(path)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(symbols: tuple[str, ...], lookback_days: int) -> tuple[pd.DataFrame, datetime]:
    end = datetime.today()
    start = end - timedelta(days=lookback_days)
    df = yf.download(
        list(symbols),
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    return df, datetime.now()


def slice_symbol(data: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if isinstance(data.columns, pd.MultiIndex):
        top = data.columns.get_level_values(0)
        if symbol not in top:
            return None
        sub = data[symbol]
    else:
        sub = data
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in sub.columns]
    sub = sub[cols].apply(pd.to_numeric, errors="coerce").dropna()
    return sub if not sub.empty else None


def evaluate(symbol: str, ohlc: pd.DataFrame) -> dict | None:
    if len(ohlc) < 252:
        return None
    ind = add_indicators(ohlc)
    ind["Signal"] = signal_mask(ind)
    last = ind.iloc[-1]

    def b(v) -> bool:
        return bool(v) if pd.notna(v) else False

    f1 = b(last["SMA150"] > last["EMA220"])
    f2 = b(last["Close"] > last["SMA50"])
    f3 = b(last["SMA50"] > last["SMA150"])
    f4 = b(last["Close"] > 1.25 * last["Low52W"])
    f5 = b(last["DipPast90"])
    breakout = b(last["Close"] > last["High52W_Prior"])

    close = float(last["Close"])
    low52 = float(last["Low52W"]) if pd.notna(last["Low52W"]) else None
    high52 = float(last["High52W_Prior"]) if pd.notna(last["High52W_Prior"]) else None

    return {
        "Symbol": symbol,
        "Date": last.name.date(),
        "Close": close,
        "SMA50": float(last["SMA50"]) if pd.notna(last["SMA50"]) else None,
        "SMA150": float(last["SMA150"]) if pd.notna(last["SMA150"]) else None,
        "EMA220": float(last["EMA220"]) if pd.notna(last["EMA220"]) else None,
        "52W High": high52,
        "52W Low": low52,
        "% Above 52W Low": ((close / low52 - 1) * 100) if low52 else None,
        "% From 52W High": ((close / high52 - 1) * 100) if high52 else None,
        "Filters Passed": int(f1 + f2 + f3 + f4 + f5),
        "F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5,
        "Breakout": breakout,
        "Signal": bool(last["Signal"]),
        "_ind": ind,
    }


def fmt_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    num_cols = [c for c in df.columns if df[c].dtype.kind in "fc"]
    fmt = {c: "{:,.2f}" for c in num_cols}
    if "% Above 52W Low" in df.columns:
        fmt["% Above 52W Low"] = "{:+.2f}%"
    if "% From 52W High" in df.columns:
        fmt["% From 52W High"] = "{:+.2f}%"
    return df.style.format(fmt, na_rep="—")


def run_download(cfg: dict, start: str, end: str | None, sleep_s: float) -> None:
    """Download all symbols for a universe, with live progress feedback."""
    out_dir = cfg["data_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    symbols = uni.load_symbols(cfg["csv"])

    progress = st.progress(0.0, text=f"Starting download of {len(symbols)} symbols…")
    log = st.empty()
    ok = fail = 0
    failures: list[str] = []

    for i, sym in enumerate(symbols, 1):
        progress.progress(i / len(symbols), text=f"[{i}/{len(symbols)}] {sym}")
        if download_symbol(sym, start, end, out_dir):
            ok += 1
        else:
            fail += 1
            failures.append(sym)
        log.caption(f"✅ {ok}   ❌ {fail}   →  {out_dir}")
        if sleep_s:
            time.sleep(sleep_s)

    progress.empty()
    if fail == 0:
        st.success(f"Downloaded {ok} symbols to {out_dir}")
    else:
        st.warning(f"Downloaded {ok}, failed {fail}: {', '.join(failures)}")
    st.cache_data.clear()


def main() -> None:
    st.set_page_config(page_title="Strategy Scanner", layout="wide")

    with st.sidebar:
        st.header("Settings")
        universe_key = st.selectbox(
            "Universe",
            options=list(uni.UNIVERSES.keys()),
            format_func=lambda k: uni.UNIVERSES[k]["label"],
            index=0,
        )
        lookback = st.number_input("Lookback days", 300, 1500, 500, 50,
                                   help="Need ≥ 252 trading days for 52-week stats.")
        if st.button("🔄 Force refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption("Yahoo Finance data is cached for 5 minutes.")

        st.divider()
        with st.expander("⬇ Download data to disk"):
            cfg_dl = uni.get(universe_key)
            dl_start = st.date_input("Start date", value=date(2023, 1, 1), key="dl_start")
            dl_end = st.date_input("End date (optional)", value=None, key="dl_end")
            sleep_s = st.number_input("Sleep between requests (s)", 0.0, 2.0, 0.2, 0.1, key="dl_sleep")
            if st.button(f"Download {cfg_dl['label']}", use_container_width=True, key="dl_btn"):
                run_download(cfg_dl, str(dl_start), str(dl_end) if dl_end else None, sleep_s)

        st.divider()
        st.subheader("Strategy filters")
        for k, v in FILTER_LABELS.items():
            st.markdown(f"**{k}** — {v}")

    cfg = uni.get(universe_key)
    st.title(f"📈 {cfg['label']} — Live Strategy Scanner")

    symbols = load_symbols(str(cfg["csv"]))
    st.caption(f"Scanning **{len(symbols)}** symbols")

    with st.spinner("Fetching live data from Yahoo Finance…"):
        data, fetched_at = fetch_history(tuple(symbols), lookback)

    rows: list[dict] = []
    skipped: list[str] = []
    for sym in symbols:
        sub = slice_symbol(data, sym)
        if sub is None:
            skipped.append(sym)
            continue
        rec = evaluate(sym, sub)
        if rec is None:
            skipped.append(sym)
            continue
        rows.append(rec)

    if not rows:
        st.error("No symbols had enough history to evaluate.")
        return

    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_ind"} for r in rows])
    indicators = {r["Symbol"]: r["_ind"] for r in rows}

    last_date = df["Date"].max()
    signals = df[df["Signal"]].sort_values("% Above 52W Low", ascending=False)
    watchlist = df[(df["Filters Passed"] == 5) & (~df["Signal"])].sort_values(
        "% From 52W High", ascending=False
    )

    age = datetime.now() - fetched_at
    age_str = f"{int(age.total_seconds())}s ago" if age.total_seconds() < 60 \
        else f"{int(age.total_seconds() // 60)}m {int(age.total_seconds() % 60)}s ago"
    st.caption(
        f"🕒 Data last refreshed: **{fetched_at.strftime('%Y-%m-%d %H:%M:%S')}** "
        f"({age_str}) · latest bar: **{last_date}**"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("As of", str(last_date))
    c2.metric("🚀 Buy signals", len(signals))
    c3.metric("👀 Watchlist", len(watchlist))
    c4.metric("Symbols evaluated", f"{len(df)} / {len(symbols)}")

    if skipped:
        with st.expander(f"Skipped {len(skipped)} symbols (insufficient history / bad data)"):
            st.write(", ".join(skipped))

    display_cols = [
        "Symbol", "Date", "Close", "SMA50", "SMA150", "EMA220",
        "52W High", "52W Low", "% Above 52W Low", "% From 52W High",
        "Filters Passed", "Breakout",
    ]

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🚀 Buy Signals", "👀 Watchlist", "📊 All Symbols", "🔍 Detail"]
    )

    with tab1:
        st.subheader("Stocks with active buy signal today")
        if signals.empty:
            st.info("No symbol satisfies all filters AND broke out to a new 52-week high today.")
        else:
            st.dataframe(fmt_table(signals[display_cols]), use_container_width=True, height=400)
            st.download_button(
                "⬇ Download signals CSV",
                signals[display_cols].to_csv(index=False).encode(),
                file_name=f"signals_{last_date}.csv",
                mime="text/csv",
            )

    with tab2:
        st.subheader("Filters pass — waiting for breakout")
        if watchlist.empty:
            st.info("No watchlist candidates.")
        else:
            st.dataframe(fmt_table(watchlist[display_cols]), use_container_width=True, height=500)

    with tab3:
        st.subheader("All evaluated symbols")
        sort_col = st.selectbox("Sort by", display_cols, index=display_cols.index("Filters Passed"))
        ascending = st.toggle("Ascending", value=False)
        all_df = df.sort_values(sort_col, ascending=ascending)
        st.dataframe(fmt_table(all_df[display_cols + ["Signal"]]), use_container_width=True, height=600)

    with tab4:
        st.subheader("Per-symbol detail")
        sym = st.selectbox("Symbol", sorted(df["Symbol"].tolist()))
        rec = df[df["Symbol"] == sym].iloc[0]
        ind = indicators[sym]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Close", f"{rec['Close']:.2f}")
        m2.metric("EMA220", f"{rec['EMA220']:.2f}" if pd.notna(rec["EMA220"]) else "—")
        m3.metric("52W High", f"{rec['52W High']:.2f}" if pd.notna(rec["52W High"]) else "—",
                  f"{rec['% From 52W High']:+.2f}%" if pd.notna(rec["% From 52W High"]) else None)
        m4.metric("52W Low", f"{rec['52W Low']:.2f}" if pd.notna(rec["52W Low"]) else "—",
                  f"{rec['% Above 52W Low']:+.2f}%" if pd.notna(rec["% Above 52W Low"]) else None)

        st.markdown("**Filter checklist**")
        cols = st.columns(6)
        checks = [("F1", rec["F1"]), ("F2", rec["F2"]), ("F3", rec["F3"]),
                  ("F4", rec["F4"]), ("F5", rec["F5"]), ("BO", rec["Breakout"])]
        for col, (key, ok) in zip(cols, checks):
            icon = "✅" if ok else "❌"
            col.markdown(f"{icon} **{key}**  \n<small>{FILTER_LABELS[key]}</small>",
                         unsafe_allow_html=True)

        st.markdown("**Price & indicators (last 252 days)**")
        chart_df = ind.tail(252)[["Close", "SMA50", "SMA150", "EMA220"]]
        st.line_chart(chart_df, height=380)


if __name__ == "__main__":
    main()
