import importlib
import py_compile
from pathlib import Path

import pytest

import config

MODULES = [
    "config", "bgos.schema", "bgos.funnel", "bgos.generate", "bgos.clean",
    "bgos.scoring", "bgos.metrics", "bgos.experiments", "bgos.cli",
    "bgos.ai.base", "bgos.ai.mock", "bgos.ai.anthropic_provider",
    "bgos.ai.research", "bgos.ai.submission_quality",
    "bgos.ai.next_best_action", "bgos.ai.email_draft",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)


def test_dashboard_compiles():
    py_compile.compile(str(config.ROOT / "app" / "dashboard.py"), doraise=True)


def test_scoring_weights_sum_to_one():
    assert sum(config.SCORING_WEIGHTS.values()) == pytest.approx(1.0)
    assert set(config.SCORING_WEIGHTS) == {
        "specialty_fit", "commercial_volume", "es_activity", "engagement", "geographic_priority"}


def test_window_and_asof():
    assert config.WINDOW_START < config.WINDOW_END
    assert config.AS_OF == config.WINDOW_END
    assert (config.WINDOW_END - config.WINDOW_START).days in (364, 365)


def test_config_basics():
    assert config.SEED == 42
    assert config.DORMANCY_DAYS == 60
    assert len(config.OWNERS) >= 3
    assert set(config.PRIORITY_STATES) <= set(config.STATE_WEIGHTS)


def test_makefile_has_required_targets():
    text = (config.ROOT / "Makefile").read_text()
    for t in ["setup", "data", "clean", "score", "metrics", "experiments",
              "ai-demo", "dashboard", "test", "all"]:
        assert f"\n{t}:" in text or text.startswith(f"{t}:"), t
