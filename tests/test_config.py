"""Config files load, validate, and reject common mistakes."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from sitescore.config import (
    BusinessProfile,
    expand_path,
    load_business_types,
    load_calendar,
    load_model_config,
    load_region,
    load_sources,
)
from sitescore.paths import CONFIG_DIR


@pytest.fixture
def cafe_raw() -> dict:
    return yaml.safe_load((CONFIG_DIR / "business_types" / "cafe.yaml").read_text(encoding="utf-8"))


def test_all_business_types_load():
    types = load_business_types()
    assert {"cafe", "gym", "childcare"} <= set(types)
    assert types["cafe"].status == "ready"


def test_montecarlo_paths_resolve_for_every_profile():
    cfg = load_model_config()
    for profile in load_business_types().values():
        data = profile.model_dump()
        for pattern in cfg.montecarlo.parameters:
            if pattern.startswith("profile."):
                assert expand_path(data, pattern.removeprefix("profile.")), (profile.id, pattern)


def test_unknown_feature_rejected(cafe_raw):
    cafe_raw["fit"]["features"]["not_a_feature"] = {"weight": 1.0}
    with pytest.raises(ValidationError, match="unknown feature"):
        BusinessProfile.model_validate(cafe_raw)


def test_typo_in_key_rejected(cafe_raw):
    cafe_raw["spend"]["avg_transaction_valu"] = 10
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(cafe_raw)


def test_daypart_shares_must_sum_to_one(cafe_raw):
    cafe_raw["dayparts"][0]["trade_share"] = 0.9
    with pytest.raises(ValidationError, match="sum to 1"):
        BusinessProfile.model_validate(cafe_raw)


def test_missing_segment_rejected(cafe_raw):
    del cafe_raw["segments"]["commuters"]
    with pytest.raises(ValidationError, match="missing segments"):
        BusinessProfile.model_validate(cafe_raw)


def test_region_and_calendar():
    region = load_region("parramatta")
    assert region.lga_code == "16260"
    cal = load_calendar(region.state)
    assert cal.school_holiday_fraction[1] > cal.school_holiday_fraction[3]


def test_sources_are_dated():
    for key, src in load_sources().items():
        if src.published_at.rule == "fixed" and src.valid_from:
            # Data can't be published before the moment it describes.
            assert src.published_at.date >= src.valid_from, key


def test_expand_path_wildcards():
    data = {"segments": {"a": {"x": 1, "flag": True}, "b": {"x": 2.5}}}
    assert sorted(expand_path(data, "segments.*.x")) == ["segments.a.x", "segments.b.x"]
    assert expand_path(data, "segments.*.flag") == []
