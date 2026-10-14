# Broker Growth OS. All data is SYNTHETIC.
PY ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)

.PHONY: setup data clean score metrics experiments ai-demo docs sweep sweep-n dashboard test all reset

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements.txt

data:        ## generate dirty synthetic data -> data/raw
	"$(PY)" -m bgos.cli data

clean:       ## dedupe / standardize / quarantine -> data/clean, outputs/data_quality_report.md
	"$(PY)" -m bgos.cli clean

score:       ## Broker Fit Score + tiers -> outputs/ranked_accounts.csv
	"$(PY)" -m bgos.cli score

metrics:     ## run every sql/*.sql -> data/marts
	"$(PY)" -m bgos.cli metrics

experiments: ## analyze experiments A/B/C -> data/marts/experiment_results.csv
	"$(PY)" -m bgos.cli experiments

ai-demo:     ## mock-provider AI demo -> outputs/ai_demo.md
	"$(PY)" -m bgos.cli ai-demo

docs:        ## DATA_DICTIONARY.md and memo numbers from generated outputs
	"$(PY)" -m bgos.cli docs

sweep:       ## 40-seed decision-rate sweep -> docs/seed_sweep.json (slow, about 10 minutes)
	"$(PY)" -m bgos.cli sweep

sweep-n:     ## N-sensitivity: 20 seeds each at N = 1500, 2000, 3000 -> docs/n_sensitivity.json (slow, about 10 minutes)
	"$(PY)" -m bgos.cli sweep-n

dashboard:
	"$(PY)" -m streamlit run app/dashboard.py

test:
	"$(PY)" -m pytest -q

all: data clean score metrics experiments ai-demo docs

reset:       ## delete generated data and outputs
	rm -rf data/raw data/clean data/marts outputs logs
