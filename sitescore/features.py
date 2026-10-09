"""Demographic features the pipeline computes for every small area (SA1).

Business profiles may only reference features listed here (the config loader
enforces it), so a new business type can mix and match without code changes.
"""

from __future__ import annotations

FEATURES: dict[str, str] = {
    "pop_total": "Usual resident population",
    "age_0_4_share": "Share of residents aged 0-4",
    "age_5_14_share": "Share of residents aged 5-14",
    "age_15_24_share": "Share of residents aged 15-24",
    "age_25_34_share": "Share of residents aged 25-34",
    "age_35_44_share": "Share of residents aged 35-44",
    "age_45_64_share": "Share of residents aged 45-64",
    "age_65_plus_share": "Share of residents aged 65+",
    "median_income_personal_weekly": "Median weekly personal income ($)",
    "median_income_household_weekly": "Median weekly household income ($)",
    "hh_family_with_children_share": "Share of households that are families with children",
    "hh_lone_or_group_share": "Share of households that are lone-person or group households",
    "dwelling_apartment_share": "Share of occupied dwellings that are flats or apartments",
    "tenure_renter_share": "Share of occupied dwellings that are rented",
    "median_rent_weekly": "Median weekly residential rent ($), a proxy for local property costs",
}
