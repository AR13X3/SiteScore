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


def test_backtest_endpoint(client):
    assert any(c["id"] == "osm" for c in client.get("/api/backtest/cohorts").json())
    r = client.post("/api/backtest", json={"cohort": "osm"}).json()
    assert r["accuracy"]["n"] == len(r["rows"]) > 0
    assert all(row["data_cutoff"] <= row["as_of"] for row in r["rows"])
    assert client.post("/api/backtest", json={"cohort": "nope"}).status_code == 404
    assert {o["outcome"] for o in r["ladder"]} >= {"actual_score", "site_churn"}


def test_cross_section_endpoint(client):
    r = client.get("/api/backtest/cross-section").json()
    assert r["time_safe"] is False and r["n"] == len(r["rows"]) > 0
    assert client.get("/api/backtest/cross-section?business_type=bowling").status_code == 404


def test_cost_overrides_change_profit_not_revenue(client):
    body = {"as_of": "2026-06-01", "sites": [CBD]}
    base = client.post("/api/simulate", json=body).json()["sites"][0]
    costs = {"rent_per_month": 0, "wages_per_month": 0, "cogs_share": 0.3,
             "other_fixed_per_month": 0}
    free = client.post("/api/simulate", json={**body, "costs": costs}).json()["sites"][0]
    assert free["total_revenue"] == pytest.approx(base["total_revenue"])
    assert free["total_profit"] == pytest.approx(0.7 * free["total_revenue"])
    assert free["total_profit"] > base["total_profit"]


def test_map_overlay_details(client):
    site = client.post("/api/simulate", json={"as_of": "2026-06-01", "sites": [CBD]}).json()
    layers = {lay["key"]: lay["details"] for lay in site["sites"][0]["mature"]["layers"]}
    assert all({"lat", "lon"} <= set(a) for a in layers["anchors"]["anchors"])
    rivals = layers["competition"]["top_competitors"]
    assert rivals and all(r["share_of_local_demand"] >= 0.001 for r in rivals)
    assert all(0 < s["straight_radius_m"] < s["radius_m"] for s in layers["demand"]["segments"].values())


def test_as_of_range(client):
    r = client.get("/api/data/as-of-range").json()
    assert r["min"] < r["max"]


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


def test_only_the_listed_site_may_call_from_another_origin(client):
    ok = client.options("/api/simulate", headers={"Origin": "https://example.github.io",
                                                  "Access-Control-Request-Method": "POST",
                                                  "Access-Control-Request-Headers": "content-type"})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://example.github.io"
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
