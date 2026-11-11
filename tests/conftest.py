"""Shared fixtures: tiny synthetic serving artefacts built with the real artefact code (no real data, no API key)."""

from __future__ import annotations

import numpy as np
import pytest

from src.data.synthetic import FEATURES, synthetic_cohort


@pytest.fixture(scope="session")
def serving_dir(tmp_path_factory):
    from src.models.baseline import prepare
    from src.models.ranking import member_value
    from src.services.artifacts import build_artifacts
    train, test = (prepare(synthetic_cohort(n, c, s)) for n, c, s in ((4000, 201702, 1), (2500, 201703, 2)))
    for d in (train, test):
        d["member_value"] = member_value(d)
    curves = {k: [[round(f, 3), 1e6 * f ** 0.5 * w] for f in np.arange(0.005, 0.5001, 0.005)] for k, w in
              (("probability", 1.0), ("expected_value", 1.001), ("lambdamart", 0.8))}
    out = tmp_path_factory.mktemp("serving")
    build_artifacts(train, test, FEATURES, out, scenarios={"members": 2500, "value_curves": curves}, tag="test")
    return out


@pytest.fixture(scope="session")
def store(serving_dir):
    from src.services.store import ServingStore
    return ServingStore(serving_dir)


@pytest.fixture()
def client(store):
    from src.genai.explain import Explainer
    from src.services.clients import LocalClient
    return LocalClient(store, Explainer())
