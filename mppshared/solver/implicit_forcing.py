""" Apply implicit forcing mechanisms to the input tables: carbon cost, green premium and technology moratorium."""

from datetime import timedelta
from timeit import default_timer as timer

import numpy as np
import pandas as pd

from mppshared.calculate.calculate_cost import discount_costs
from mppshared.config import EMISSION_SCOPES, GHGS
from mppshared.import_data.intermediate_data import IntermediateDataImporter
from mppshared.model.carbon_cost_trajectory import CarbonCostTrajectory
from mppshared.utility.dataframe_utility import (
    add_column_header_suffix, get_grouping_columns_for_npv_calculation)
from mppshared.utility.function_timer_utility import timer_func
from mppshared.utility.log_utility import get_logger

logger = get_logger("Apply implicit forcing")


# def apply_implicit_forcing(
#     df_technology_switches: pd.DataFrame,
#     df_emissions: pd.DataFrame,
#     df_technology_characteristics: pd.DataFrame,
# ) -> pd.DataFrame:
def apply_implicit_forcing(
    pathway: str, sensitivity: str, product: str, sector: str
) -> pd.DataFrame:
    """Apply the implicit forcing mechanisms to the input tables.

    Args:
        df_technology_switches: cost data for every technology switch (regional)
        df_emissions: emissions data for every technology (regional)
        df_technology_characteristics: characteristics for every technology

    Returns:
        pd.DataFrame: DataFrame ready for ranking the technology switches
    """

    # Add carbon cost to TCO
    # TODO: improve runtime
    importer = IntermediateDataImporter(
        pathway=pathway, sensitivity=sensitivity, sector=sector, product=product
    )
    df_technology_switches = importer.get_tech_transitions()
    df_emissions = importer.get_emissions()
    df_technology_characteristics = importer.get_plant_specs()
    start = timer()
    df_carbon_cost = apply_carbon_cost_to_tco(
        df_technology_switches, df_emissions, df_technology_characteristics
    )
    end = timer()
    logger.info(
        f"Time elapsed to apply carbon cost to {len(df_carbon_cost)} rows: {timedelta(seconds=end-start)}"
    )

    # TODO: add carbon cost to LCOX and other cost metrics

    # TODO: Subtract green premium from eligible technologies

    # TODO: Eliminate switches according to technology moratorium

    # Apply technology availability constraint
    # df = apply_technology_availability_constraint(df_technology_switches, df_technology_characteristics)

    # Calculate emission deltas between origin and destination technology
    df_ranking = calculate_emission_reduction(df_carbon_cost, df_emissions)
    importer.export_data(df=df_ranking, filename="technologies_to_rank.csv")

    return df_ranking


@timer_func
def apply_carbon_cost_to_tco(
    df_technology_switches: pd.DataFrame,
    df_emissions: pd.DataFrame,
    df_technology_characteristics: pd.DataFrame,
) -> pd.DataFrame:
    """

    Args:
        df_technology_switches: cost data for every technology switch (regional)
        df_emissions: emissions data for every technology (regional)
        df_technology_characteristics: characteristics for every technology

    Returns:
        pd.DataFrame: merge of the input DataFrames with additional column "carbon_cost_addition" added to TCO
    """
    # Drop emission columns with other GHGs
    for ghg in [ghg for ghg in GHGS if ghg != "co2"]:
        df_emissions = df_emissions.drop(df_emissions.filter(regex=ghg).columns)

    # Merge technology switches, emissions and technology characteristics
    df = df_technology_switches.merge(
        df_emissions.rename(columns={"technology": "technology_destination"}),
        on=["product", "region", "year", "technology_destination"],
        how="left",
    )

    df = df.merge(
        df_technology_characteristics.rename(
            columns={"technology": "technology_destination"}
        ),
        on=["product", "region", "technology_destination"],
        how="left",
    )

    # Additional cost from carbon cost is carbon cost multiplied with sum of scope 1 and scope 2 CO2 emissions
    cc = CarbonCostTrajectory(
        trajectory="constant", initial_carbon_cost=50, final_carbon_cost=50
    )
    df_cc = df.merge(cc.df_carbon_cost, on=["year"])
    df_cc["carbon_cost_addition"] = (df_cc["co2_scope1"] + df_cc["co2_scope2"]) * df_cc[
        "carbon_cost"
    ]

    # Discount carbon cost addition
    # TODO: make grouping column function sector-specific
    grouping_cols = get_grouping_columns_for_npv_calculation("chemicals")

    df_discounted = discount_costs(
        df_cc[
            grouping_cols
            + ["year", "carbon_cost_addition", "technology_lifetime", "wacc"]
        ],
        grouping_cols,
    )

    # Add total discounted carbon cost to each technology switch
    df = df.set_index(grouping_cols + ["year"])
    df["carbon_cost_addition"] = df_discounted["carbon_cost_addition"]

    # Contribution of a cost to TCO is net present cost divided by (lifetime * capacity utilisation factor)
    # TODO: integrate dynamic capacity utilisation functionality
    capacity_factor_dummy = 0.95
    df["carbon_cost_addition_tco"] = (
        df["carbon_cost_addition"] / (df["technology_lifetime"] * capacity_factor_dummy)
    ).fillna(0)

    # Update TCO in technology switching DataFrame
    df_technology_switches = df_technology_switches.set_index(grouping_cols + ["year"])
    df_technology_switches["tco"] = df["tco"] + df["carbon_cost_addition_tco"]

    # Return technology switch DataFrame with updated TCO
    return df_technology_switches.reset_index(drop=False)


def apply_technology_availability_constraint(
    df_technology_switches: pd.DataFrame, df_technology_characteristics: pd.DataFrame
) -> pd.DataFrame:
    """_summary_

    Args:
        df_technology_switches (pd.DataFrame): _description_
        df_technology_characteristics (pd.DataFrame): _description_

    Returns:
        pd.DataFrame: _description_
    """
    pass


def calculate_emission_reduction(
    df_technology_switches: pd.DataFrame, df_emissions: pd.DataFrame
) -> pd.DataFrame:
    """Calculate emission reduction when switching from origin to destination technology by scope.

    Args:
        df_technology_switches (pd.DataFrame): cost data for every technology switch (regional)
        df_emissions (pd.DataFrame): emissions data for every technology

    Returns:
        pd.DataFrame: contains "delta_{}" for every scope and GHG considered
    """
    # Get columns containing emissions
    cols = [f"{ghg}_{scope}" for ghg in GHGS for scope in EMISSION_SCOPES]

    # Rename column headers for origin and destination technology emissions and drop captured emissions columns
    df_emissions_origin = add_column_header_suffix(
        df_emissions.drop(df_emissions.filter(regex="captured").columns, axis=1),
        cols,
        "origin",
    )

    df_emissions_destination = add_column_header_suffix(
        df_emissions.drop(df_emissions.filter(regex="captured").columns, axis=1),
        cols,
        "destination",
    )

    # Merge to insert origin and destination technology emissions into technology switching table
    df = df_technology_switches.merge(
        df_emissions_origin.rename(columns={"technology": "technology_origin"}),
        on=["product", "region", "year", "technology_origin"],
        how="left",
    )

    df = df.merge(
        df_emissions_destination.rename(
            columns={"technology": "technology_destination"}
        ),
        on=["product", "technology_destination", "region", "year"],
        how="left",
    )

    # Calculate emissions reduction for each technology switch by GHG and scope
    for ghg in GHGS:
        for scope in EMISSION_SCOPES:
            df[f"delta_{ghg}_{scope}"] = df[f"{ghg}_{scope}_origin"].fillna(0) - df[
                f"{ghg}_{scope}_destination"
            ].fillna(0)

    # Drop emissions of destination and origin technology
    drop_cols = [
        f"{ghg}_{scope}_{switch_locator}"
        for switch_locator in ["origin", "destination"]
        for ghg in GHGS
        for scope in EMISSION_SCOPES
    ]
    df = df.drop(columns=drop_cols)

    return df
