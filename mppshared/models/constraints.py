""" Enforce constraints in the yearly optimization of technology switches."""
from copy import deepcopy

import numpy as np
import pandas as pd
from pandera import Bool
from pyparsing import col

from mppshared.config import (
    END_YEAR,
    LOG_LEVEL,
    REGIONAL_PRODUCTION_SHARES,
    YEAR_2050_EMISSIONS_CONSTRAINT,
)
from mppshared.models.asset import Asset, AssetStack
from mppshared.models.simulation_pathway import SimulationPathway
from mppshared.utility.utils import get_logger

logger = get_logger(__name__)
logger.setLevel(LOG_LEVEL)


def check_constraints(
    pathway: SimulationPathway,
    stack: AssetStack,
    year: int,
    transition_type: str,
) -> dict:
    """Check all constraints for a given asset stack and return dictionary of Booleans with constraint types as keys.

    Args:
        pathway: contains data on demand and resource availability
        stack: stack of assets for which constraints are to be checked
        product
        year: required for resource availabilities
        transition_type: either of "decommission", "brownfield", "greenfield"

    Returns:
        Returns True if no constraint hurt
    """
    # TODO: Map constraint application to the three transition types

    # Check regional production constraint
    # TODO: is this still needed for any of the transition types?
    # regional_constraint = check_constraint_regional_production(
    #     pathway=pathway, stack=stack, product=product, year=year
    # )

    # If pathway not bau, then check for constraints, else return true
    if pathway.pathway != "bau":
        # Check constraint for annual emissions limit from carbon budget
        emissions_constraint, flag_residual = check_annual_carbon_budget_constraint(
            pathway=pathway, stack=stack, year=year, transition_type=transition_type
        )
        # Check technology ramp-up constraint
        rampup_constraint = check_technology_rampup_constraint(
            pathway=pathway, stack=stack, year=year
        )

        # Check CO2 storage constraint
        co2_storage_constraint = check_co2_storage_constraint(
            pathway=pathway, stack=stack, year=year
        )

        # Check constraint on annual addition of electrolysis capacity
        electrolysis_capacity_addition_constraint = (
            check_electrolysis_capacity_addition_constraint(
                pathway=pathway, stack=stack, year=year
            )
        )

        # TODO Remove this workaround
        emissions_constraint = True
        # TODO: Check resource availability constraint
        return {
            "emissions_constraint": emissions_constraint,
            "rampup_constraint": rampup_constraint,
            "co2_storage_constraint": co2_storage_constraint,
            "electrolysis_capacity_addition_constraint": electrolysis_capacity_addition_constraint,
        }
    else:
        return {"emissions_constraint": True, "rampup_constraint": True}


def check_electrolysis_capacity_addition_constraint(
    pathway: SimulationPathway, stack: AssetStack, year: int
) -> Bool:
    """Check if the annual addition of electrolysis capacity fulfills the constraint"""

    # Get annual production capacities per technology of current and tentative new stack
    df_capacity_old_stack = (
        pathway.stacks[year]
        .aggregate_stack(
            aggregation_vars=["technology"], technology_classification="end-state"
        )["annual_production_capacity"]
        .reset_index()
    )
    df_capacity_new_stack = stack.aggregate_stack(aggregation_vars=["technology"])[
        "annual_production_capacity"
    ].reset_index()

    # Sum for electrolysis technologies
    capacity_old_stack = df_capacity_old_stack.loc[
        df_capacity_old_stack["technology"].str.contains("Electrolyser")
    ].sum()["annual_production_capacity"]
    capacity_new_stack = df_capacity_new_stack.loc[
        df_capacity_new_stack["technology"].str.contains("Electrolyser")
    ].sum()["annual_production_capacity"]

    # Compare to electrolysis capacity addition constraint in that year
    capacity_addition = capacity_new_stack - capacity_old_stack
    df_constr = (
        pathway.importer.get_electrolysis_capacity_addition_constraint().set_index(
            "year"
        )
    )
    capacity_addition_constraint = df_constr.loc[year, "value"]

    if capacity_addition <= capacity_addition_constraint:
        return True

    logger.debug("Annual electrolysis capacity addition constraint hurt.")
    return False


def check_co2_storage_constraint(
    pathway: SimulationPathway, stack: AssetStack, year: int
) -> Bool:
    """Check if the constraint on total CO2 storage (globally) is met"""

    # Calculate CO2 captured annually by the stack (Mt CO2)
    co2_captured = stack.calculate_co2_captured_stack(
        year=year, df_emissions=pathway.emissions
    )

    # Compare with the limit on annual CO2 storage addition (MtCO2)
    df_co2_storage = pathway.co2_storage_constraint
    limit = df_co2_storage.loc[df_co2_storage["year"] == year, "value"].item()

    if limit > co2_captured:
        return True

    logger.debug("CO2 storage constraint hurt.")
    return False


def check_technology_rampup_constraint(
    pathway: SimulationPathway, stack: AssetStack, year: int
) -> Bool:
    """Check if the technology rampup between the stacked passed and the previous year's stack complies with the technology ramp-up trajectory

    Args:
        pathway: contains the stack of the previous year
        stack: new stack for which the ramp-up constraint is to be checked
        year: year corresponding to the stack passed
    """
    # Get asset numbers of new and old stack for each technology
    df_old_stack = (
        pathway.stacks[year]
        .aggregate_stack(aggregation_vars=["technology"])[["number_of_assets"]]
        .rename({"number_of_assets": "number_old"}, axis=1)
    )
    df_new_stack = stack.aggregate_stack(aggregation_vars=["technology"])[
        ["number_of_assets"]
    ].rename({"number_of_assets": "number_new"}, axis=1)

    # Create DataFrame for rampup comparison
    df_rampup = df_old_stack.join(df_new_stack, how="outer").fillna(0)
    df_rampup["proposed_asset_additions"] = (
        df_rampup["number_new"] - df_rampup["number_old"]
    )
    for technology in df_rampup.index:
        rampup_constraint = pathway.technology_rampup[technology]
        if rampup_constraint:
            df_rampup.loc[
                technology, "maximum_asset_additions"
            ] = rampup_constraint.df_rampup.loc[year, "maximum_asset_additions"]
        else:
            df_rampup.loc[technology, "maximum_asset_additions"] = None

    df_rampup["check"] = (
        df_rampup["proposed_asset_additions"] <= df_rampup["maximum_asset_additions"]
    ) | (df_rampup["maximum_asset_additions"].isna())

    if df_rampup["check"].all():
        return True

    technology_affected = list(df_rampup[df_rampup["check"] == False].index)
    logger.debug(f"Technology ramp-up constraint hurt for {technology_affected}.")
    return False


def check_constraint_regional_production(
    pathway: SimulationPathway, stack: AssetStack, product: str, year: int
) -> Bool:
    """Check constraints that regional production is at least a specified share of regional demand

    Args:
        stack (_type_): _description_
        product (_type_): _description_
    """
    df = get_regional_production_constraint_table(pathway, stack, product, year)
    # The constraint is hurt if any region does not meet its required regional production share
    if df["check"].all():
        return True

    return False


def get_regional_production_constraint_table(
    pathway: SimulationPathway, stack: AssetStack, product: str, year: int
) -> pd.DataFrame:
    """Get table that compares regional production with regional demand for a given year"""

    # Get regional production and demand
    df_regional_production = stack.get_regional_production_volume(product)
    df_demand = pathway.get_regional_demand(product, year)

    # Check for every region in DataFrame
    df = df_regional_production.merge(df_demand, on=["region"], how="left")
    df["share_regional_production"] = df["region"].map(
        REGIONAL_PRODUCTION_SHARES[pathway.sector]
    )

    # Add required regional production column
    df["annual_production_volume_minimum"] = (
        df["demand"] * df["share_regional_production"]
    )

    # Compare regional production with required demand share up to specified number of significant figures
    sf = 2
    df["check"] = np.round(df["annual_production_volume"], sf) >= np.round(
        df["annual_production_volume_minimum"], sf
    )
    return df


def check_annual_carbon_budget_constraint(
    pathway: SimulationPathway, stack: AssetStack, year: int, transition_type: str
) -> Bool:
    """Check if the stack exceeds the Carbon Budget defined in the pathway for the given product and year"""

    # After a sector-specific year, all end-state newbuild capacity has to fulfill the 2050 emissions limit with a stack composed of only end-state technologies
    if (transition_type == "greenfield") & (
        year >= YEAR_2050_EMISSIONS_CONSTRAINT[pathway.sector]
    ):
        limit = pathway.carbon_budget.get_annual_emissions_limit(
            END_YEAR, pathway.sector
        )

        dict_stack_emissions = stack.calculate_emissions_stack(
            year=year,
            df_emissions=pathway.emissions,
            technology_classification="end-state",
        )
        flag_residual = True

    # In other cases, the limit is equivalent to that year's emission limit
    else:
        limit = pathway.carbon_budget.get_annual_emissions_limit(year, pathway.sector)

        dict_stack_emissions = stack.calculate_emissions_stack(
            year=year, df_emissions=pathway.emissions, technology_classification=None
        )
        flag_residual = False

    # Compare scope 1 and 2 CO2 emissions to the allowed limit in that year
    co2_scope1_2 = (
        dict_stack_emissions["co2_scope1"] + dict_stack_emissions["co2_scope2"]
    ) / 1e3  # Gt CO2

    if np.round(co2_scope1_2, 2) <= np.round(limit, 2):
        return True, flag_residual

    return False, flag_residual
