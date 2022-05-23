""" Apply implicit forcing mechanisms to the input tables: carbon cost, green premium and technology moratorium."""

from datetime import timedelta
from pathlib import Path
from re import M
from timeit import default_timer as timer
import numpy as np
import pandas as pd

from mppshared.calculate.calculate_cost import discount_costs
from mppshared.config import (
    CARBON_COST_ADDITION_FROM_CSV,
    EMISSION_SCOPES,
    GHGS,
    PATHWAYS,
    PRODUCTS,
    RANKING_COST_METRIC,
    REGIONAL_TECHNOLOGY_BAN,
    REGIONS_SALT_CAVERN_AVAILABILITY,
    SCOPES_CO2_COST,
    SENSITIVITIES,
    START_YEAR,
    TECHNOLOGY_MORATORIUM,
    TRANSITIONAL_PERIOD_YEARS,
)
from mppshared.import_data.intermediate_data import IntermediateDataImporter
from mppshared.models.carbon_cost_trajectory import CarbonCostTrajectory
from mppshared.solver.input_loading import filter_df_for_development
from mppshared.utility.dataframe_utility import (
    add_column_header_suffix,
    get_grouping_columns_for_npv_calculation,
)
from mppshared.utility.function_timer_utility import timer_func
from mppshared.utility.log_utility import get_logger

logger = get_logger(__name__)


def apply_implicit_forcing(
    pathway: str, sensitivity: str, sector: str, carbon_cost: CarbonCostTrajectory
) -> pd.DataFrame:
    """Apply the implicit forcing mechanisms to the input tables.

    Args:
        pathway:
        sensitivity:
        sector:

    Returns:
        pd.DataFrame: DataFrame ready for ranking the technology switches
    """
    logger.info("Applying implicit forcing")

    # Import input tables
    importer = IntermediateDataImporter(
        pathway=pathway,
        sensitivity=sensitivity,
        sector=sector,
        products=PRODUCTS[sector],
        carbon_cost=carbon_cost,
    )

    df_technology_switches = importer.get_technology_transitions_and_cost()
    df_emissions = importer.get_emissions()
    df_technology_characteristics = importer.get_technology_characteristics()

    # Apply technology availability constraint
    df_technology_switches = apply_technology_availability_constraint(
        df_technology_switches, df_technology_characteristics
    )

    # Eliminate technologies with geological H2 storage in regions without salt caverns
    df_technology_switches = apply_salt_cavern_availability_constraint(
        df_technology_switches, sector
    )

    # Apply technology moratorium (year after which newbuild capacity must be transition or
    # end-state technologies)
    if pathway != "bau":
        df_technology_switches = apply_technology_moratorium(
            df_technology_switches=df_technology_switches,
            df_technology_characteristics=df_technology_characteristics,
            moratorium_year=TECHNOLOGY_MORATORIUM[sector],
            transitional_period_years=TRANSITIONAL_PERIOD_YEARS[sector],
        )
    # Add technology classification
    else:
        df_technology_switches = df_technology_switches.merge(
            df_technology_characteristics[
                ["product", "year", "region", "technology", "technology_classification"]
            ].rename({"technology": "technology_destination"}, axis=1),
            on=["product", "year", "region", "technology_destination"],
            how="left",
        )
    df_cc = carbon_cost.df_carbon_cost
    if df_cc["carbon_cost"].sum() == 0:
        df_carbon_cost = df_technology_switches.copy()
    else:
        # TODO: loads of hardcoded stuff!
        # Write carbon cost addition to csv in first run for subsequent multiplication
        if df_cc.loc[df_cc["year"] == 2025, "carbon_cost"].item() == 1:

            start = timer()
            # df_technology_switches = filter_df_for_development(df_technology_switches)
            df_carbon_cost_addition = calculate_carbon_cost_addition_to_cost_metric(
                df_technology_switches=df_technology_switches,
                df_emissions=df_emissions,
                df_technology_characteristics=df_technology_characteristics,
                cost_metric=RANKING_COST_METRIC[sector],
                df_carbon_cost=df_cc,
            )
            end = timer()
            logger.info(
                f"Time elapsed to apply carbon cost to {len(df_carbon_cost_addition)} rows: {timedelta(seconds=end-start)}"
            )

            # Write carbon cost to all intermediate folders
            for folder in [
                f"{pathway}/{sensitivity}"
                for sensitivity in SENSITIVITIES
                for pathway in PATHWAYS
            ]:
                parent_path = Path(__file__).resolve().parents[2]
                path = parent_path.joinpath(
                    f"data/{sector}/{folder}/intermediate/carbon_cost_addition.csv"
                )
                df_carbon_cost_addition.to_csv(path, index=False)
        else:
            df_carbon_cost_addition = importer.get_carbon_cost_addition()

        # Update cost metric in technology switching DataFrame with carbon cost
        cost_metric = RANKING_COST_METRIC[sector]
        merge_cols = [
            "product",
            "technology_origin",
            "technology_destination",
            "region",
            "switch_type",
            "year",
        ]
        df_carbon_cost = df_technology_switches.merge(
            df_carbon_cost_addition[
                merge_cols + [f"carbon_cost_addition_{cost_metric}"]
            ],
            on=merge_cols,
            how="left",
        )
        # Carbon cost addition is for 1 USD/tCO2, hence multiply with right factor
        constant_carbon_cost = df_cc.loc[df_cc["year"] == 2025, "carbon_cost"].item()
        df_carbon_cost[f"carbon_cost_addition_{cost_metric}"] = (
            df_carbon_cost[f"carbon_cost_addition_{cost_metric}"] * constant_carbon_cost
        )

        df_carbon_cost[cost_metric] = (
            df_carbon_cost[cost_metric]
            + df_carbon_cost[f"carbon_cost_addition_{cost_metric}"]
        )

    # Calculate emission deltas between origin and destination technology
    df_ranking = calculate_emission_reduction(df_carbon_cost, df_emissions)
    importer.export_data(
        df=df_ranking,
        filename="technologies_to_rank.csv",
        export_dir="intermediate",
        index=False,
    )

    return df_ranking


def apply_salt_cavern_availability_constraint(
    df_technology_transitions: pd.DataFrame, sector: str
) -> pd.DataFrame:
    """Take out technologies with geological H2 storage in regions that do not have salt cavern availability"""
    if sector not in REGIONS_SALT_CAVERN_AVAILABILITY.keys():
        return df_technology_transitions

    salt_cavern_availability = REGIONS_SALT_CAVERN_AVAILABILITY[sector]
    for region in [
        reg for reg in salt_cavern_availability if salt_cavern_availability[reg] == "no"
    ]:
        filter = (df_technology_transitions["region"] == region) & (
            (
                df_technology_transitions["technology_destination"].str.contains(
                    "H2 storage - geological"
                )
                | (
                    df_technology_transitions["technology_origin"].str.contains(
                        "H2 storage - geological"
                    )
                )
            )
        )

        df_technology_transitions = df_technology_transitions.loc[~filter]

    return df_technology_transitions


@timer_func
def calculate_carbon_cost_addition_to_cost_metric(
    df_technology_switches: pd.DataFrame,
    df_emissions: pd.DataFrame,
    df_technology_characteristics: pd.DataFrame,
    cost_metric: str,
    df_carbon_cost: pd.DataFrame,
) -> pd.DataFrame:
    """Apply constant carbon cost to a cost metric.

    Args:
        df_technology_switches: cost data for every technology switch (regional)
        df_emissions: emissions data for every technology (regional)
        df_technology_characteristics: characteristics for every technology

    Returns:
        pd.DataFrame: merge of the input DataFrames with additional column "carbon_cost_addition" added to TCO
    """
    # Drop emission columns with other GHGs
    for ghg in [ghg for ghg in GHGS if ghg != "co2"]:
        df_emissions = df_emissions.drop(columns=df_emissions.filter(regex=ghg).columns)

    # Merge technology switches, emissions and technology characteristics
    df = df_technology_switches.merge(
        df_emissions.rename(columns={"technology": "technology_destination"}),
        on=["product", "region", "year", "technology_destination"],
        how="left",
    ).fillna(0)

    df = df.merge(
        df_technology_characteristics.rename(
            columns={"technology": "technology_destination"}
        ),
        on=["product", "region", "year", "technology_destination"],
        how="left",
    ).fillna(0)

    # Additional cost from carbon cost is carbon cost multiplied with sum of the co2 emission scopes included in the optimization
    df = df.merge(df_carbon_cost, on=["year"], how="left")
    df["sum_co2_emissions"] = 0
    for scope in SCOPES_CO2_COST:
        df["sum_co2_emissions"] += df[f"co2_{scope}"]
    df["carbon_cost_addition"] = df["sum_co2_emissions"] * df["carbon_cost"]

    # Discount carbon cost addition
    # TODO: make grouping column function sector-specific
    grouping_cols = get_grouping_columns_for_npv_calculation("chemicals")

    df_discounted = discount_costs(
        df[
            grouping_cols
            + ["year", "carbon_cost_addition", "technology_lifetime", "wacc"]
        ],
        grouping_cols,
    )

    # Add total discounted carbon cost to each technology switch
    df = df.set_index(grouping_cols + ["year"])
    df["carbon_cost_addition"] = df_discounted["carbon_cost_addition"]

    if cost_metric == "tco":
        # Contribution of a cost to TCO is net present cost divided by (lifetime * capacity utilisation factor)
        # TODO: integrate dynamic capacity utilisation functionality
        cuf_dummy = 0.95
        df["carbon_cost_addition_tco"] = (
            df["carbon_cost_addition"] / (df["technology_lifetime"] * cuf_dummy)
        ).fillna(0)

        # Update TCO in technology switching DataFrame
        df_technology_switches = df_technology_switches.set_index(
            grouping_cols + ["year"]
        )
        df_technology_switches["tco"] = df["tco"] + df["carbon_cost_addition_tco"]

    elif cost_metric == "lcox":
        # Contribution of a cost to LCOX is net present cost divided by (CUF * total discounted production)
        # TODO: ensure that sector-specific
        cuf = 0.95
        rate = df_technology_characteristics["wacc"].unique()[0]
        lifetime = df_technology_characteristics["technology_lifetime"].unique()[0]
        value_shares = (1 + rate) ** np.arange(0, lifetime + 1)
        total_discounted_production = np.sum(1 / value_shares)

        df["carbon_cost_addition_lcox"] = (
            df["carbon_cost_addition"] / (cuf * total_discounted_production)
        ).fillna(0)

    # Return technology switch DataFrame with carbon cost addition
    # TODO: improve this workaround
    return df.reset_index(drop=False).drop(
        columns=[
            "technology_classification_x",
            "technology_classification_y",
            "wacc",
            "trl_current",
            "technology_lifetime",
        ]
    )


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

    # Add classification of origin and destination technologies to technology transitions table
    df_tech_char_destination = df_technology_characteristics[
        ["product", "year", "region", "technology", "technology_classification"]
    ].rename(
        {
            "technology": "technology_destination",
            "technology_classification": "classification_destination",
        },
        axis=1,
    )

    df_tech_char_origin = df_technology_characteristics[
        ["product", "year", "region", "technology", "technology_classification"]
    ].rename(
        {
            "technology": "technology_origin",
            "technology_classification": "classification_origin",
        },
        axis=1,
    )
    df = df_technology_switches.merge(
        df_tech_char_destination,
        on=["product", "year", "region", "technology_destination"],
        how="left",
    ).fillna(0)
    df = df.merge(
        df_tech_char_origin,
        on=["product", "year", "region", "technology_origin"],
        how="left",
    ).fillna(0)

    # Constraint 1: no switches from transition or end-state to initial technologies
    df = df.loc[
        ~(
            (
                (df["classification_origin"] == "transition")
                & (df["classification_destination"] == "initial")
            )
            | (
                (df["classification_origin"] == "end-state")
                & (df["classification_destination"] == "initial")
            )
            | (
                (df["classification_origin"] == "end-state")
                & (df["classification_destination"] == "transition")
            )
        )
    ]

    # Constraint 2: transitions to a technology are only possible when it has reached maturity
    df = df.merge(
        df_technology_characteristics[
            ["product", "year", "region", "technology", "expected_maturity"]
        ].rename({"technology": "technology_destination"}, axis=1),
        on=["product", "year", "region", "technology_destination"],
        how="left",
    ).fillna(START_YEAR)
    df = df.loc[df["year"] >= df["expected_maturity"]]

    # Constraint 3: no transitions between end-state technologies
    df = df.loc[
        ~(
            (df["classification_destination"] == "end-state")
            & (df["classification_origin"] == "end-state")
        )
    ]

    return df.drop(
        columns=[
            "classification_origin",
            "classification_destination",
            "expected_maturity",
        ]
    )


def apply_regional_technology_ban(
    df_technology_switches: pd.DataFrame, sector_bans: dict
) -> pd.DataFrame:
    """Remove certain technologies from the technology switching table that are banned in certain regions (defined in config.py)"""
    if not sector_bans:
        return df_technology_switches
    for region in sector_bans.keys():
        banned_transitions = (df_technology_switches["region"] == region) & (
            df_technology_switches["technology_destination"].isin(sector_bans[region])
        )
        df_technology_switches = df_technology_switches.loc[~banned_transitions]
    return df_technology_switches


def apply_technology_moratorium(
    df_technology_switches: pd.DataFrame,
    df_technology_characteristics: pd.DataFrame,
    moratorium_year: int,
    transitional_period_years: int,
) -> pd.DataFrame:
    """Eliminate all newbuild transitions to a conventional technology after a specific year

    Args:
        df_technology_switches (pd.DataFrame): df_technology_switches
        df_technology_characteristics (pd.DataFrame): df_technology_characteristics
        moratorium_year (int): Year from which the technology moratorium kicks in
        transitional_period_years (int): Period during transition to transition technologies is allowed

    Returns:
        pd.DataFrame:
    """

    # Add technology classification to each destination technology
    df_tech_char_destination = df_technology_characteristics[
        ["product", "year", "region", "technology", "technology_classification"]
    ].rename(
        {"technology": "technology_destination"},
        axis=1,
    )
    df_technology_switches = df_technology_switches.merge(
        df_tech_char_destination,
        on=["product", "year", "region", "technology_destination"],
        how="left",
    ).fillna(0)

    # Drop technology transitions of type new-build where the technology_destination is classified as initial
    banned_transitions = (
        (df_technology_switches["year"] >= moratorium_year)
        & (df_technology_switches["technology_classification"] == "initial")
        & (df_technology_switches["switch_type"] != "decommission")
    )
    df_technology_switches = df_technology_switches.loc[~banned_transitions]

    # Drop technology transitions for 'transition' technologies after moratorium year + x years
    banned_transitions = (
        (df_technology_switches["year"] >= moratorium_year + transitional_period_years)
        & (df_technology_switches["technology_classification"] == "transition")
        & (df_technology_switches["switch_type"] != "decommission")
    )
    df_technology_switches = df_technology_switches.loc[~banned_transitions]

    return df_technology_switches


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
    # Get columns containing emissions and filter emissions table accordingly
    cols = [f"{ghg}_{scope}" for ghg in GHGS for scope in EMISSION_SCOPES]
    df_emissions = df_emissions[["product", "technology", "year", "region"] + cols]

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

    # Merge to insert origin and destination technology emissions into technology switching table (fill with zero to account for new-build and decommission)
    df = df_technology_switches.merge(
        df_emissions_origin.rename(columns={"technology": "technology_origin"}),
        on=["product", "region", "year", "technology_origin"],
        how="left",
    ).fillna(0)

    df = df.merge(
        df_emissions_destination.rename(
            columns={"technology": "technology_destination"}
        ),
        on=["product", "technology_destination", "region", "year"],
        how="left",
    ).fillna(0)

    # Calculate emissions reduction for each technology switch by GHG and scope
    for ghg in GHGS:
        for scope in EMISSION_SCOPES:
            df[f"delta_{ghg}_{scope}"] = df[f"{ghg}_{scope}_origin"].fillna(0) - df[
                f"{ghg}_{scope}_destination"
            ].fillna(0)

    # Drop emissions of destination and origin technology
    # drop_cols = [
    #     f"{ghg}_{scope}_{switch_locator}"
    #     for switch_locator in ["origin", "destination"]
    #     for ghg in GHGS
    #     for scope in EMISSION_SCOPES
    # ]
    # df = df.drop(columns=drop_cols)

    return df
