"""Command line entry point used by the Makefile: python -m bgos.cli <command>."""
from __future__ import annotations

import argparse
import sys


def run_pipeline(root=None, docs: bool = True) -> None:
    """Whole synthetic pipeline (used by `make all` equivalents and by the dashboard's first-run bootstrap)."""
    from . import clean, experiments, generate, metrics, scoring
    from .ai import demo
    generate.generate(root)
    clean.run_clean(root)
    scoring.run_score(root)
    metrics.run_all(root)
    experiments.run_experiments(root)
    demo.run_demo(root)
    if docs:
        from . import docs as _docs
        _docs.run_docs(root)


def bootstrap_once(root=None, timeout: float = 600.0) -> None:
    """Run the pipeline once even if several sessions ask at the same time (lock file, O_EXCL)."""
    import os
    import time
    import config
    paths = config.get_paths(root).ensure()
    lock = paths.root / "data" / ".bootstrap.lock"
    done = paths.marts / "topline.csv"
    deadline = time.time() + timeout
    while not done.exists():
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.time() > deadline:
                raise TimeoutError("another session is generating the data and did not finish")
            time.sleep(0.2)
            continue
        try:
            if not done.exists():
                run_pipeline(root, docs=False)
        finally:
            os.close(fd)
            os.unlink(lock)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bgos", description="Broker Growth OS (all data is SYNTHETIC)")
    ap.add_argument("command", choices=["data", "clean", "score", "metrics", "experiments", "ai-demo", "docs", "all", "sweep"])
    ap.add_argument("--root", default=None, help="output root (default: repo, or $BGOS_ROOT)")
    a = ap.parse_args(argv)
    if a.command == "data":
        from . import generate
        res = generate.generate(a.root)
        print(f"generated {len(res['raw']['agencies'])} agency rows, {len(res['raw']['touches'])} touches, "
              f"{len(res['raw']['submissions'])} submissions (SYNTHETIC)")
    elif a.command == "clean":
        from . import clean
        res = clean.run_clean(a.root)
        print(f"cleaned: {len(res.agencies)} agencies, {len(res.submissions)} submissions, "
              f"{len(res.quarantine)} quarantine entries")
    elif a.command == "score":
        from . import scoring
        r = scoring.run_score(a.root)
        print("tiers:", r.tier.value_counts().to_dict())
    elif a.command == "metrics":
        from . import metrics
        out = metrics.run_all(a.root)
        print(f"wrote {len(out)} metric marts")
    elif a.command == "experiments":
        from . import experiments
        df = experiments.run_experiments(a.root)
        print(df[["experiment_id", "rel_lift", "p_value", "decision"]].to_string(index=False), "\n(SIMULATED results)")
    elif a.command == "ai-demo":
        from .ai import demo
        demo.run_demo(a.root)
        print("wrote outputs/ai_demo.md")
    elif a.command == "sweep":
        from . import sweep
        print(sweep.run_sweep()["summary"])
    elif a.command == "all":
        run_pipeline(a.root)
        print("pipeline complete (SYNTHETIC data)")
    elif a.command == "docs":
        from . import docs
        docs.run_docs(a.root)
        print("wrote DATA_DICTIONARY.md, STRATEGY_MEMO.md and LOOM_SCRIPT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
