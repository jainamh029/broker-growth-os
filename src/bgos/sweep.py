"""Seed sweep: how often does each experiment return each decision across simulated datasets?

One dataset (seed 42) is ONE simulated draw of a design with imperfect power; this sweep shows the spread.
`make sweep` regenerates docs/seed_sweep.json (about 10 minutes for 40 seeds). SYNTHETIC data only.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import config

SEEDS = tuple(range(1, 41))


def run_one(seed: int) -> dict:
    from . import clean, experiments, generate, metrics, scoring
    root = Path(tempfile.mkdtemp(prefix=f"bgos_sweep_{seed}_"))
    try:
        generate.generate(root=root, seed=seed)
        clean.run_clean(root)
        scoring.run_score(root)
        metrics.run_all(root)
        df = experiments.run_experiments(root).set_index("experiment_id")
        return {k: {"rel_lift": round(float(df.loc[k, "rel_lift"]), 6), "p_value": round(float(df.loc[k, "p_value"]), 6),
                    "decision": str(df.loc[k, "decision"])} for k in "ABC"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def summarize(seeds: dict[str, dict]) -> dict:
    n = len(seeds)
    out = {"n_seeds": n}
    for k in "ABC":
        c = Counter(v[k]["decision"] for v in seeds.values())
        out[k] = {"decisions": dict(sorted(c.items())),
                  "significant_p_lt_0.05": sum(v[k]["p_value"] < 0.05 for v in seeds.values()),
                  "mean_rel_lift": round(sum(v[k]["rel_lift"] for v in seeds.values()) / n, 4)}
    return out


def run_sweep(seeds=SEEDS, workers: int = 3, path: Path | None = None) -> dict:
    with ProcessPoolExecutor(workers) as ex:
        results = list(ex.map(run_one, seeds))
    per_seed = {str(s): r for s, r in zip(seeds, results)}
    doc = {"note": "SYNTHETIC. One dataset per seed; planted effects A +30%, B +15%, C 0.",
           "summary": summarize(per_seed), "seeds": per_seed}
    path = path or (config.ROOT / "docs" / "seed_sweep.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return doc
