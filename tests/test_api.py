"""API smoke tests against the mock dataset."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from sitescore.api.deps import get_store
from sitescore.api.main import app

CBD = {"label": "CBD", "lat": -33.8150, "lon": 151.0035}
HARRIS_PARK = {"label": "Harris Park", "lat": -33.8226, "lon": 151.0085}


@pytest.fixture(scope="module")
def client(mock_store):
    app.dependency_overrides[get_store] = lambda: mock_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_and_data_status(client):
    assert client.get("/api/health").json()["status"] == "ok"
    status = {t["table"]: t for t in client.get("/api/data/status").json()}
    assert status["areas"]["provenance"] == "mock"
    assert status["places"]["model_visible"] is False


def test_evaluate_returns_explained_results(client):
    resp = client.post("/api/evaluate", json={"business_type": "cafe", "as_of": "2026-06-01",
                                              "sites": [CBD, HARRIS_PARK]})
    assert resp.status_code == 200
    results = resp.json()
    assert [r["site"]["id"] for r in results] == ["site-1", "site-2"]
    for r in results:
        assert {"demand", "fit", "anchors", "competition", "spend"} <= {l["key"] for l in r["layers"]}
        assert math.prod(l["factor"] for l in r["layers"]) == pytest.approx(r["monthly_revenue"])
        assert all(d["latest_published"] <= "2026-06-01" for d in r["data_used"])


def test_simulate_returns_36_months_ranking_and_why(client):
    resp = client.post("/api/simulate", json={"as_of": "2026-06-01",
                                              "sites": [CBD, HARRIS_PARK]})
    assert resp.status_code == 200
    r = resp.json()
    assert r["open_date"] == "2026-07-01"
    assert all(len(s["months"]) == 36 for s in r["sites"])
    assert set(r["ranking"]) == {"site-1", "site-2"}
    assert all(e["headline"] for e in r["explanations"])


def test_simulate_with_uncertainty_bands(client):
    r = client.post("/api/simulate", json={"as_of": "2026-06-01", "uncertainty": True,
                                           "sites": [CBD, HARRIS_PARK]}).json()
    u = r["uncertainty"]
    assert u["n_runs"] > 0 and len(u["sites"]) == 2
    assert all(len(s["revenue"]["p10"]) == 36 for s in u["sites"])
    assert sum(s["prob_best"] for s in u["sites"]) == pytest.approx(1.0)


def test_unknown_business_type_is_404(client):
    resp = client.post("/api/evaluate", json={"business_type": "bowling", "sites": [CBD]})
    assert resp.status_code == 404


def test_as_of_before_data_existed_is_422_with_reason(client):
    resp = client.post("/api/evaluate", json={"as_of": "2021-01-01", "sites": [CBD]})
    assert resp.status_code == 422
    assert "no 'areas' release published on or before 2021-01-01" in resp.json()["detail"]


def test_site_count_limits(client):
    assert client.post("/api/evaluate", json={"sites": []}).status_code == 422
    assert client.post("/api/evaluate", json={"sites": [CBD] * 6}).status_code == 422
