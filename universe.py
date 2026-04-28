"""Universe registry: maps a universe key to its symbols CSV, data dir, and currency."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
TICKERS_DIR = ROOT / "tickers"

UNIVERSES: dict[str, dict] = {
    "nasdaq100": {
        "label": "NASDAQ 100",
        "csv": TICKERS_DIR / "NASDAQ100.csv",
        "data_dir": ROOT / "data" / "nasdaq100",
        "results_dir": ROOT / "results" / "nasdaq100",
        "currency": "$",
    },
    "nifty50": {
        "label": "Nifty 50",
        "csv": TICKERS_DIR / "NIFTY50.csv",
        "data_dir": ROOT / "data" / "nifty50",
        "results_dir": ROOT / "results" / "nifty50",
        "currency": "₹",
    },
    "midcap150": {
        "label": "Nifty Midcap 150",
        "csv": TICKERS_DIR / "MIDCAP150.csv",
        "data_dir": ROOT / "data" / "midcap150",
        "results_dir": ROOT / "results" / "midcap150",
        "currency": "₹",
    },
    "smallcap250": {
        "label": "Nifty Smallcap 250",
        "csv": TICKERS_DIR / "SMALLCAP250.csv",
        "data_dir": ROOT / "data" / "smallcap250",
        "results_dir": ROOT / "results" / "smallcap250",
        "currency": "₹",
    },
}


def get(universe: str) -> dict:
    key = universe.lower()
    if key not in UNIVERSES:
        raise ValueError(f"Unknown universe '{universe}'. Choices: {list(UNIVERSES)}")
    return UNIVERSES[key]


def load_symbols(csv_path) -> list[str]:
    """Read a symbols CSV ('Symbol' column). Tolerates surrounding quotes / whitespace."""
    df = pd.read_csv(csv_path)
    cleaned = (
        df["Symbol"].dropna().astype(str)
        .str.strip().str.strip('"\'').str.strip()
        .str.upper()
    )
    return [s for s in cleaned.unique().tolist() if s]
