"""ABS Census 2021 General Community Profile -> `areas` (one row per SA1)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from sitescore.pipeline import abs_geo
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import download
from sitescore.pipeline.mock_world import mock_world

AGE_BANDS = ("age_0_4_share", "age_5_14_share", "age_15_24_share", "age_25_34_share",
             "age_35_44_share", "age_45_64_share", "age_65_plus_share")

# Census columns (DataPack short headers) summed into each age band.
AGE_COLUMNS = {
    "age_0_4_share": ["Age_0_4_yr_P"],
    "age_5_14_share": ["Age_5_14_yr_P"],
    "age_15_24_share": ["Age_15_19_yr_P", "Age_20_24_yr_P"],
    "age_25_34_share": ["Age_25_34_yr_P"],
    "age_35_44_share": ["Age_35_44_yr_P"],
    "age_45_64_share": ["Age_45_54_yr_P", "Age_55_64_yr_P"],
    "age_65_plus_share": ["Age_65_74_yr_P", "Age_75_84_yr_P", "Age_85ov_P"],
}


def read_table(zip_path: Path, table: str, geo: str = "SA1") -> pd.DataFrame:
    """One DataPack table (e.g. G01), all columns, codes kept as strings."""
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(f"_{table}_{_state(zip_path)}_{geo}.csv"))
        return pd.read_csv(z.open(name), dtype={f"{geo}_CODE_2021": str})


def _state(zip_path: Path) -> str:
    return zip_path.stem.split("_for_")[1].split("_")[0]


def _share(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den.where(den > 0)).clip(0, 1)


def census_features(zip_path: Path) -> pd.DataFrame:
    """Demographic features per SA1 (FEATURES in sitescore/features.py)."""
    g01, g02 = read_table(zip_path, "G01"), read_table(zip_path, "G02")
    g36, g37, g42 = (read_table(zip_path, t) for t in ("G36", "G37", "G42"))
    pop = g01["Tot_P_P"]
    out = pd.DataFrame({"sa1_code": g01["SA1_CODE_2021"], "pop_total": pop.astype(float)})
    for feature, cols in AGE_COLUMNS.items():
        out[feature] = _share(g01[cols].sum(axis=1), pop)
    out = out.merge(pd.DataFrame({
        "sa1_code": g02["SA1_CODE_2021"],
        "median_income_personal_weekly": g02["Median_tot_prsnl_inc_weekly"],
        "median_income_household_weekly": g02["Median_tot_hhd_inc_weekly"],
    }), on="sa1_code", how="left")
    hh = g42["Tot_Tot"]
    out = out.merge(pd.DataFrame({
        "sa1_code": g42["SA1_CODE_2021"],
        "hh_family_with_children_share": _share(g42["Tot_FHs_CF_C"] + g42["Tot_FHs_OnePF"], hh),
        "hh_lone_or_group_share": _share(g42["Tot_Lone_P_H"] + g42["Tot_Group_H"], hh),
    }), on="sa1_code", how="left")
    out = out.merge(pd.DataFrame({
        "sa1_code": g36["SA1_CODE_2021"],
        "dwelling_apartment_share": _share(g36["OPDs_Flt_apart_Tot_Dwgs"],
                                           g36["OPDs_Tot_OPDs_Dwellings"]),
    }), on="sa1_code", how="left")
    total_col = "Total_Total" if "Total_Total" in g37 else g37.columns[-1]
    return out.merge(pd.DataFrame({
        "sa1_code": g37["SA1_CODE_2021"],
        "tenure_renter_share": _share(g37["R_Tot_Total"], g37[total_col]),
    }), on="sa1_code", how="left")


def fill_gaps(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Small or empty SA1s have suppressed/zero values: use the population-weighted median."""
    df = df.copy()
    w = df["pop_total"].clip(lower=0)
    for col in columns:
        bad = df[col].isna() | ((df[col] <= 0) & col.startswith("median"))
        good = df.loc[~bad, [col]].assign(w=w[~bad]).sort_values(col)
        if good.empty:
            continue
        cum = good["w"].cumsum()
        median = good[col].iloc[int(np.searchsorted(cum, cum.iloc[-1] / 2))]
        df.loc[bad, col] = median
    return df


class AbsCensus(Adapter):
    source_id = "abs_census_gcp"
    tables = ("areas",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        src = ctx.source(self.source_id)
        url = src.model_extra["url"]
        zip_path = download(url, ctx.raw_dir / self.source_id / url.rsplit("/", 1)[1])
        sa1 = abs_geo.sa1s(ctx)
        lon, lat = abs_geo.centroids(sa1)
        geo = pd.DataFrame({"sa1_code": sa1["sa1_code"], "sa2_code": sa1["sa2_code"],
                            "lon": lon, "lat": lat, "area_sqkm": sa1["area_sqkm"]})
        df = geo.merge(census_features(zip_path), on="sa1_code", how="left")
        df["pop_total"] = df["pop_total"].fillna(0)
        feature_cols = [c for c in df.columns if c.endswith("_share") or c.startswith("median")]
        df = fill_gaps(df, feature_cols)
        return {"areas": stamp(df, published_at=src.published_at.date,
                               valid_from=src.valid_from, version=src.valid_from)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        city = mock_world(ctx).city
        rng = np.random.default_rng(ctx.seed("areas"))
        n = 650
        lat, lon = city.sample(n, rng, job_mix=0.0)
        apt = np.clip(city.density(lat, lon, "apartments") + rng.normal(0, 0.08, n), 0, 0.97)

        # Age mix: apartment areas skew towards young adults, houses towards families.
        base = np.array([0.07, 0.12, 0.12, 0.19, 0.16, 0.21, 0.13])
        tilt = np.array([0.0, -0.5, 0.2, 0.8, 0.2, -0.4, -0.3])
        alpha = 80 * base[None, :] * np.exp(tilt[None, :] * (apt[:, None] - 0.4))
        ages = np.vstack([rng.dirichlet(a) for a in alpha])

        income_p = np.clip(rng.normal(780 + 420 * apt, 110), 350, 2200)
        density = city.density(lat, lon, "residents")
        lon_min, lat_min, lon_max, lat_max = ctx.region.bbox
        bbox_km2 = (lon_max - lon_min) * 92.6 * (lat_max - lat_min) * 110.5

        df = pd.DataFrame({
            "sa1_code": [f"MOCK-SA1-{i:04d}" for i in range(n)],
            "sa2_code": [f"MOCK-SA2-{c:02d}" for c in city.nearest_centre(lat, lon)],
            "lon": lon,
            "lat": lat,
            "area_sqkm": bbox_km2 / n * density.mean() / density,
            "pop_total": np.clip(rng.normal(400, 90, n), 150, 900).round(),
            **{band: ages[:, i] for i, band in enumerate(AGE_BANDS)},
            "median_income_personal_weekly": income_p.round(),
            "median_income_household_weekly":
                np.clip(income_p * rng.normal(2.3 - 0.5 * apt, 0.15), 700, 5000).round(),
            "hh_family_with_children_share": np.clip(0.48 - 0.30 * apt + rng.normal(0, 0.05, n), 0.03, 0.8),
            "hh_lone_or_group_share": np.clip(0.17 + 0.22 * apt + rng.normal(0, 0.04, n), 0.03, 0.7),
            "dwelling_apartment_share": apt,
            "tenure_renter_share": np.clip(0.25 + 0.45 * apt + rng.normal(0, 0.06, n), 0.05, 0.9),
        })
        src = ctx.source(self.source_id)
        return {"areas": stamp(df, published_at=src.published_at.date,
                               valid_from=src.valid_from, version=src.valid_from)}
