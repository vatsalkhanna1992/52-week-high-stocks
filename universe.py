"""Universe registry: maps a universe key to its symbols CSV, data dir, and currency."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent

UNIVERSES: dict[str, dict] = {
    "nasdaq100": {
        "label": "NASDAQ 100",
        "csv": ROOT / "NASDAQ100.csv",
        "data_dir": ROOT / "data" / "nasdaq100",
        "results_dir": ROOT / "results" / "nasdaq100",
        "currency": "$",
    },
    "nifty50": {
        "label": "Nifty 50",
        "csv": ROOT / "Nifty50.csv",
        "data_dir": ROOT / "data" / "nifty50",
        "results_dir": ROOT / "results" / "nifty50",
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
