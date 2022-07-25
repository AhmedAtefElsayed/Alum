"""Year-by-year optimisation logic of plant investment decisions to simulate a pathway for the ammonia supply technology mix."""

from datetime import timedelta
from timeit import default_timer as timer

from ammonia.config_ammonia import (ANNUAL_RENOVATION_SHARE,
                                    ASSUMED_ANNUAL_PRODUCTION_CAPACITY,
                                    CARBON_BUDGET_SECTOR_CSV,
                                    CONSTRAINTS_TO_APPLY, CUF_LOWER_THRESHOLD,
                                    CUF_UPPER_THRESHOLD, EMISSION_SCOPES,
                                    END_YEAR, GHGS, INITIAL_ASSET_DATA_LEVEL,
                                    INVESTMENT_CYCLE, LOG_LEVEL,
                                    MAXIMUM_GLOBAL_DEMAND_SHARE, PRODUCTS,
                                    RANK_TYPES, REGIONAL_PRODUCTION_SHARES,
                                    SECTORAL_CARBON_PATHWAY, START_YEAR,
                                    TECHNOLOGIES_MAXIMUM_GLOBAL_DEMAND_SHARE,
                                    TECHNOLOGY_RAMP_UP_CONSTRAINT,
                                    YEAR_2050_EMISSIONS_CONSTRAINT)
from ammonia.solver.brownfield import brownfield
from ammonia.solver.decommission import decommission
from ammonia.solver.greenfield import greenfield
from mppshared.agent_logic.agent_logic_functions import (
    adjust_capacity_utilisation, create_dict_technology_rampup)
from mppshared.config import SECTORAL_CARBON_BUDGETS
from mppshared.import_data.intermediate_data import IntermediateDataImporter
from mppshared.models.carbon_budget import CarbonBudget
from mppshared.models.carbon_cost_trajectory import CarbonCostTrajectory
from mppshared.models.simulation_pathway import SimulationPathway
from mppshared.utility.log_utility import get_logger

logger = get_logger(__name__)
logger.setLevel(LOG_LEVEL)


def simulate(pathway: SimulationPathway) -> SimulationPathway:
    """
    Run the pathway simulation over the years
    Args:
        pathway: The decarbonization pathway

    Returns:
        The updated pathway with the asset stack in each year of the model horizon
    """

    # Run pathway simulation in each year for all products simultaneously
    for year in range(START_YEAR, END_YEAR + 1):
        logger.info("Optimizing for %s", year)

        # Adjust capacity utilisation of each asset
        pathway = adjust_capacity_utilisation(pathway=pathway, year=year)

        # Copy over last year's stack to this year
        pathway = pathway.copy_stack(year=year)

        # Write stack to csv
        pathway.export_stack_to_csv(year)

        # Decommission assets
        start = timer()
        pathway = decommission(pathway=pathway, year=year)
        end = timer()
        logger.debug(
            f"Time elapsed for decommission in year {year}: {timedelta(seconds=end-start)} seconds"
        )

        # Renovate and rebuild assets (brownfield transition)
        start = timer()
        pathway = brownfield(pathway=pathway, year=year)
        end = timer()
        logger.debug(
            f"Time elapsed for brownfield in year {year}: {timedelta(seconds=end-start)} seconds"
        )

        # Build new assets
        start = timer()
        pathway = greenfield(pathway=pathway, year=year)
        end = timer()
        logger.debug(
            f"Time elapsed for greenfield in year {year}: {timedelta(seconds=end-start)} seconds"
        )

    return pathway


def simulate_pathway(
    sector: str,
    pathway: str,
    sensitivity: str,
    carbon_cost_trajectory: CarbonCostTrajectory,
):
    """
    Get data per technology, ranking data and then run the pathway simulation
    """
    importer = IntermediateDataImporter(
        pathway=pathway,
        sensitivity=sensitivity,
        sector=sector,
        products=PRODUCTS,
        carbon_cost_trajectory=carbon_cost_trajectory,
    )

    # Create carbon budget
    carbon_budget = CarbonBudget(
        start_year=START_YEAR,
        end_year=END_YEAR,
        sectoral_carbon_budgets=SECTORAL_CARBON_BUDGETS,
        pathway_shape="linear",
        sector=sector,
        carbon_budget_sector_csv=CARBON_BUDGET_SECTOR_CSV,
        sectoral_carbon_pathway=SECTORAL_CARBON_PATHWAY,
        importer=importer,
    )

    # Create technology ramp-up trajectory for each technology in the form of a dictionary
    dict_technology_rampup = create_dict_technology_rampup(
        importer=importer,
        model_start_year=START_YEAR,
        model_end_year=END_YEAR,
        maximum_asset_additions=TECHNOLOGY_RAMP_UP_CONSTRAINT[
            "maximum_asset_additions"
        ],
        maximum_capacity_growth_rate=TECHNOLOGY_RAMP_UP_CONSTRAINT[
            "maximum_capacity_growth_rate"
        ],
        years_rampup_phase=TECHNOLOGY_RAMP_UP_CONSTRAINT["years_rampup_phase"],
    )

    # Make pathway
    pathway = SimulationPathway(
        start_year=START_YEAR,
        end_year=END_YEAR,
        pathway=pathway,
        sensitivity=sensitivity,
        sector=sector,
        products=PRODUCTS,
        rank_types=RANK_TYPES,
        initial_asset_data_level=INITIAL_ASSET_DATA_LEVEL,
        assumed_annual_production_capacity=ASSUMED_ANNUAL_PRODUCTION_CAPACITY,
        technology_rampup=dict_technology_rampup,
        carbon_budget=carbon_budget,
        carbon_cost_trajectory=carbon_cost_trajectory,
        emission_scopes=EMISSION_SCOPES,
        cuf_lower_threshold=CUF_LOWER_THRESHOLD,
        cuf_upper_threshold=CUF_UPPER_THRESHOLD,
        ghgs=GHGS,
        regional_production_shares=REGIONAL_PRODUCTION_SHARES,
        constraints_to_apply=CONSTRAINTS_TO_APPLY,
        year_2050_emissions_constraint=YEAR_2050_EMISSIONS_CONSTRAINT,
        investment_cycle=INVESTMENT_CYCLE,
        annual_renovation_share=ANNUAL_RENOVATION_SHARE,
        technologies_maximum_global_demand_share=TECHNOLOGIES_MAXIMUM_GLOBAL_DEMAND_SHARE,
        maximum_global_demand_share=MAXIMUM_GLOBAL_DEMAND_SHARE,
    )

    # Optimize asset stack on a yearly basis
    pathway = simulate(
        pathway=pathway,
    )
    pathway.output_technology_roadmap()
    logger.info("Pathway simulation complete")
