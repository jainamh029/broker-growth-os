import pytest

import config
from bgos import generate


@pytest.fixture(scope="session")
def gen_result(tmp_path_factory):
    """One generated dataset (written to a temp dir) shared across tests."""
    root = tmp_path_factory.mktemp("gen")
    res = generate.generate(root=root)
    res["root"] = root
    return res


@pytest.fixture(scope="session")
def clean_result(gen_result):
    from bgos import clean
    res = clean.run_clean(gen_result["root"])
    return res
