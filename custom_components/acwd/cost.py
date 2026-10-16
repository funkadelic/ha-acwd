"""Hourly water cost statistic, priced from the hourly usage statistic."""

from __future__ import annotations

from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)

from .const import DOMAIN, HCF_TO_GALLONS


def cost_metadata(meter_number: str) -> StatisticMetaData:
    """Return metadata for the hourly cost statistic; currency comes from the HA config."""
    return StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=f"ACWD Water Hourly Cost - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{meter_number}_hourly_cost",
        unit_class=None,
        unit_of_measurement=None,
    )


def build_cost_statistics(usage: list[StatisticData], baseline: float, rate_per_unit: float) -> list[StatisticData]:
    """Price each usage hour (gallons) at rate_per_unit per 748-gallon unit, continuing the sum from baseline."""
    cost_sum = baseline
    costs: list[StatisticData] = []
    for stat in usage:
        cost = stat["state"] / HCF_TO_GALLONS * rate_per_unit
        cost_sum += cost
        costs.append(StatisticData(start=stat["start"], sum=cost_sum, state=cost))
    return costs
