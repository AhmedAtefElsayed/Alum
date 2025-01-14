""" Logic for technology transitions of type brownfield rebuild and brownfield renovation."""
import random
import sys
from copy import deepcopy
from operator import methodcaller

import numpy as np
import pandas as pd
from ammonia.config_ammonia import (
    ANNUAL_RENOVATION_SHARE,
    BROWNFIELD_REBUILD_START_YEAR,
    BROWNFIELD_RENOVATION_START_YEAR,
    COST_METRIC_DECREASE_BROWNFIELD,
    LOG_LEVEL,
    RANKING_COST_METRIC,
    REGIONAL_TECHNOLOGY_BAN,
    SWITCH_TYPES_UPDATE_YEAR_COMMISSIONED,
)
from mppshared.agent_logic.agent_logic_functions import (
    apply_regional_technology_ban,
    remove_all_transitions_with_destination_technology,
    remove_transition,
    select_best_transition,
)
from mppshared.agent_logic.brownfield import (
    apply_brownfield_filters_ammonia,
    apply_start_years_brownfield_transitions,
)
from mppshared.models.constraints import check_constraints
from mppshared.models.simulation_pathway import SimulationPathway
from mppshared.utility.log_utility import get_logger
from pandera import Bool

logger = get_logger(__name__)
logger.setLevel(LOG_LEVEL)


def brownfield(pathway: SimulationPathway, year: int) -> SimulationPathway:
    """Apply brownfield rebuild or brownfield renovation transition to eligible Assets in the AssetStack.

    Args:
        pathway: decarbonization pathway that describes the composition of the AssetStack in every year of the model horizon
        year: current year in which technology transitions are enacted
        product: product for which technology transitions are enacted

    Returns:
        Updated decarbonization pathway with the updated AssetStack in the subsequent year according to the brownfield transitions enacted
    """
    logger.debug(f"Starting brownfield transition logic for year {year}")

    # Next year's asset stack is changed by the brownfield transitions
    new_stack = pathway.get_stack(year=year + 1)

    # Get ranking table for brownfield transitions
    df_rank = pathway.get_ranking(year=year, rank_type="brownfield")

    # Apply filters for the ammonia sector
    df_rank = apply_brownfield_filters_ammonia(
        df_rank,
        pathway,
        year,
        ranking_cost_metric=RANKING_COST_METRIC,
        cost_metric_decrease_brownfield=COST_METRIC_DECREASE_BROWNFIELD,
    )

    # Apply regional technology ban
    df_rank = apply_regional_technology_ban(
        df_rank, sector_bans=REGIONAL_TECHNOLOGY_BAN
    )

    # Apply start years of brownfield transitions
    df_rank = apply_start_years_brownfield_transitions(
        df_rank=df_rank,
        pathway=pathway,
        year=year,
        brownfield_renovation_start_year=BROWNFIELD_RENOVATION_START_YEAR,
        brownfield_rebuild_start_year=BROWNFIELD_REBUILD_START_YEAR,
    )

    # Get assets eligible for brownfield transitions
    candidates = new_stack.get_assets_eligible_for_brownfield(
        year=year,
        investment_cycle=pathway.investment_cycle,
    )

    # Track number of assets that undergo transition to ensure that it stays below the revamp rate
    n_assets_transitioned = 0
    maximum_n_assets_transitioned = np.ceil(
        ANNUAL_RENOVATION_SHARE * new_stack.get_number_of_assets()
    )

    logger.debug(
        f"Number of assets eligible for brownfield transition: {len(candidates)} in year {year}, of which maximum {maximum_n_assets_transitioned} can be transitioned."
    )

    # Enact brownfield transitions while there are still candidates and the revamp rate is not exceeded
    while (candidates != []) & (n_assets_transitioned <= maximum_n_assets_transitioned):

        # Find assets can undergo the best transition. If there are no assets for the best transition, continue searching with the next-best transition
        best_candidates = []  # type: list
        while not best_candidates:

            # If no more transitions available, break and return pathway
            if df_rank.empty:
                return pathway

            # Choose the best transition, i.e. highest decommission rank
            best_transition = select_best_transition(df_rank)

            best_candidates = list(
                filter(
                    lambda asset: (
                        asset.technology == best_transition["technology_origin"]
                    )
                    & (asset.region == best_transition["region"])
                    & (asset.product == best_transition["product"]),
                    candidates,
                )
            )
            new_technology = best_transition["technology_destination"]
            switch_type = best_transition["switch_type"]

            # Remove best transition from ranking table (other assets could undergo the same transition)
            df_rank = remove_transition(df_rank, best_transition)

        # If several candidates for best transition, choose asset for transition randomly
        asset_to_update = random.choice(best_candidates)

        # Update asset tentatively (needs deepcopy to provide changes to original stack)
        tentative_stack = deepcopy(new_stack)
        origin_technology = asset_to_update.technology
        tentative_stack.update_asset(
            year=year,
            asset_to_update=deepcopy(asset_to_update),
            new_technology=new_technology,
            new_classification=best_transition["technology_classification"],
            asset_lifetime=best_transition["technology_lifetime"],
            switch_type=switch_type,
            origin_technology=origin_technology,
            update_year_commission=False,
        )

        # Check constraints with tentative new stack
        dict_constraints = check_constraints(
            pathway=pathway,
            stack=tentative_stack,
            year=year,
            transition_type="brownfield",
            product=best_transition["product"],
        )

        # If no constraint is hurt, execute the brownfield transition
        if all(constraint == True for constraint in dict_constraints.values()):
            logger.debug(
                f"Updating {asset_to_update.product} asset from technology {origin_technology} to technology {new_technology} in region {asset_to_update.region}, annual production {asset_to_update.get_annual_production_volume()} and UUID {asset_to_update.uuid}"
            )
            # Set retrofit or rebuild attribute to True according to type of brownfield transition
            if best_transition["switch_type"] == "brownfield_renovation":
                asset_to_update.retrofit = True
            if best_transition["switch_type"] == "brownfield_newbuild":
                asset_to_update.rebuild = True

            # Update asset stack
            new_stack.update_asset(
                year=year,
                asset_to_update=asset_to_update,
                new_technology=new_technology,
                new_classification=best_transition["technology_classification"],
                asset_lifetime=best_transition["technology_lifetime"],
                switch_type=switch_type,
                origin_technology=origin_technology,
                update_year_commission=(
                    switch_type in SWITCH_TYPES_UPDATE_YEAR_COMMISSIONED
                ),
            )

            # Remove asset from candidates
            candidates.remove(asset_to_update)
            n_assets_transitioned += 1

        # ELECTROLYSIS CAPACITY ADDITION
        elif (
            "electrolysis_capacity_addition_constraint" in pathway.constraints_to_apply
        ):
            if not dict_constraints["electrolysis_capacity_addition_constraint"]:
                # Remove all transitions with that destination technology from the ranking table
                logger.debug(
                    f"Handle electrolysis capacity addition constraint: removing destination technology"
                )
                df_rank = remove_all_transitions_with_destination_technology(
                    df_rank, best_transition["technology_destination"]
                )

        # CO2 STORAGE
        elif "co2_storage_constraint" in pathway.constraints_to_apply:
            if not dict_constraints["co2_storage_constraint"]:
                # Remove all transitions with that destination technology from the ranking table
                logger.debug(
                    f"Handle CO2 storage constraint: removing destination technology"
                )
                df_rank = remove_all_transitions_with_destination_technology(
                    df_rank, best_transition["technology_destination"]
                )

        # GLOBAL DEMAND SHARE
        elif "demand_share_constraint" in pathway.constraints_to_apply:
            if not dict_constraints["demand_share_constraint"]:
                # Remove all transitions with that destination technology from the ranking table
                logger.debug(
                    f"Handle global demand share constraint: removing destination technology"
                )
                df_rank = remove_all_transitions_with_destination_technology(
                    df_rank, best_transition["technology_destination"]
                )

    logger.debug(f"{n_assets_transitioned} assets transitioned in year {year}.")

    return pathway
