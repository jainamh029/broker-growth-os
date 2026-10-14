"""Output rounding rule: every float written to a mart CSV or embedded in a page is rounded to 10 SIGNIFICANT digits.

Why: different Python/numpy/scipy builds differ in the last 1-2 bits of a float (p = 2.2567328784098436e-05 vs 2.256732878409844e-05), which
would make a committed page differ from a regeneration elsewhere. 10 significant digits removes that noise (about 1e-16 relative) yet keeps
money to the cent below 1e8 and p-values to 10 digits. The statistics themselves are computed at full precision; this is applied only at output.
"""
from __future__ import annotations

import math

import pandas as pd

SIG_DIGITS = 10


def round_sig(x: float, digits: int = SIG_DIGITS) -> float:
    if x is None or not isinstance(x, float) or not math.isfinite(x) or x == 0.0:
        return x
    return float(f"{x:.{digits}g}")


def round_df(df: pd.DataFrame, digits: int = SIG_DIGITS) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].map(lambda v: round_sig(float(v), digits) if pd.notna(v) else v)
    return out


def round_obj(o, digits: int = SIG_DIGITS):
    """Recursively round floats in dicts/lists (for JSON embedded in pages)."""
    if isinstance(o, float):
        return round_sig(o, digits)
    if isinstance(o, dict):
        return {k: round_obj(v, digits) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [round_obj(v, digits) for v in o]
    return o
