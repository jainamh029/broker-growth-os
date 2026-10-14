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


def run_one(seed: int, n_agencies: int | None = None, extended: bool = False) -> dict:
    """One simulated dataset -> experiment results. extended=True adds required and achieved n per arm (used by the N-sensitivity sweep)."""
    from . import clean, experiments, generate, metrics, scoring
    root = Path(tempfile.mkdtemp(prefix=f"bgos_sweep_{seed}_"))
    try:
        generate.generate(root=root, seed=seed, n_agencies=n_agencies)
        clean.run_clean(root)
        scoring.run_score(root)
        metrics.run_all(root)
        df = experiments.run_experiments(root).set_index("experiment_id")
        out = {k: {"rel_lift": round(float(df.loc[k, "rel_lift"]), 6), "p_value": round(float(df.loc[k, "p_value"]), 6),
                   "decision": str(df.loc[k, "decision"])} for k in "ABC"}
        if extended:
            for k in "ABC":
                out[k]["n_required"] = int(df.loc[k, "n_required_per_arm"])
                out[k]["n_per_arm"] = int(min(df.loc[k, "n_control"], df.loc[k, "n_treatment"]))
        return out
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


N_VALUES = (1500, 2000, 3000)
N_SEEDS = tuple(range(1, 21))


def _run_n(args):
    n, seed = args
    return run_one(seed, n_agencies=n, extended=True)


def summarize_n(per_seed: dict) -> dict:
    out = {}
    for n, seeds in per_seed.items():
        out[n] = {}
        for k in "ABC":
            c = Counter(v[k]["decision"] for v in seeds.values())
            out[n][k] = {"decisions": dict(sorted(c.items())),
                         "mean_required_per_arm": round(sum(v[k]["n_required"] for v in seeds.values()) / len(seeds)),
                         "mean_achieved_per_arm": round(sum(v[k]["n_per_arm"] for v in seeds.values()) / len(seeds))}
    return out


def run_sweep_n(n_values=N_VALUES, seeds=N_SEEDS, workers: int = 3, path: Path | None = None) -> dict:
    """Sensitivity of the experiment decisions to the number of agencies (the default N is NOT changed)."""
    jobs = [(n, s) for n in n_values for s in seeds]
    with ProcessPoolExecutor(workers) as ex:
        results = list(ex.map(_run_n, jobs))
    per_seed: dict = {str(n): {} for n in n_values}
    for (n, s), r in zip(jobs, results):
        per_seed[str(n)][str(s)] = r
    doc = {"note": "SYNTHETIC. Decisions of experiments A/B/C vs number of agencies; default N is 3000 (brief: about 1500).",
           "seeds": list(seeds), "summary": summarize_n(per_seed), "per_seed": per_seed}
    path = path or (config.ROOT / "docs" / "n_sensitivity.json")
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return doc


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
