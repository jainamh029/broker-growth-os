# DECISIONS

Decision log. Every judgment call made without human input is recorded here. All data is synthetic.

| # | Phase | Decision | Why |
|---|-------|----------|-----|
| D1 | 0 | Venv scripts are invoked as `python -m ...` (never via `.venv/bin/pytest` shebangs). | The workspace path contains spaces, which breaks shebang lines. `python -m` works everywhere. |
| D2 | 0 | `config.get_paths()` honours a `BGOS_ROOT` env var. | Lets tests and the README-quickstart test run the whole pipeline in a temp dir without touching the repo's `data/`. |
| D3 | 0 | Makefile `clean` means "run the data-cleaning stage" (per the brief's target list); `reset` deletes generated files. | Brief lists `data, clean, score...` as pipeline steps. |
