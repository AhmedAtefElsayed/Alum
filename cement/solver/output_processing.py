""" Process outputs to standardised output table."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
from cement.config.config_cement import (
    ASSUMED_ANNUAL_PRODUCTION_CAPACITY,
    CCUS_CONTEXT,
    COAL_GJ_T,
    ELECTRICITY_GJ_TWH,
    EMISSION_SCOPES,
    END_YEAR,
    GHGS,
    GROSS_BIO_EMISSION_FACTOR,
    HYDROGEN_GJ_T,
    MODEL_YEARS,
    NATURAL_GAS_GJ_BCM,
    PRODUCTS,
    RECARBONATION_SHARE,
    SECTOR,
    START_YEAR,
)
from cement.config.output_config_cement import (
    ASSUMED_CARBON_CAPTURE_RATE,
    MAP_EMISSION_FACTOR_PRE_CAPTURE,
    RESOURCE_CONSUMPTION_METRICS,
    TECHNOLOGY_LAYOUT,
)
from mppshared.config import LOG_LEVEL
from mppshared.import_data.intermediate_data import IntermediateDataImporter
from mppshared.utility.log_utility import get_logger
from plotly.offline import plot

logger = get_logger(__name__)
logger.setLevel(LOG_LEVEL)


def aggregate_outputs(
    runs: list,
    sector: str,
):
    """Aggregates and exports all outputs from all runs"""

    df_list = []

    for pathway_name, sensitivity in runs:

        logger.info(f"Aggregating outputs for {pathway_name}_{sensitivity}")

        importer = IntermediateDataImporter(
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            sector=sector,
            products=PRODUCTS,
        )
        df_tech_roadmap = _create_tech_roadmaps_by_region(
            importer=importer, start_year=START_YEAR, end_year=END_YEAR
        )
        df_resource_consumption_gj = _calculate_resource_consumption_gj(
            importer=importer
        )
        df_resource_consumption_clkprod_only_gj = _calculate_resource_consumption_gj(
            importer=importer, clinker_production_only=True
        )
        df_emissions = _calculate_emissions_total(
            importer=importer,
            ghgs=GHGS,
            emission_scopes=EMISSION_SCOPES,
            format_data=False,
        )

        # tech roadmap
        logger.info("-- Technology roadmap")
        df_tech_roadmap_formatted = _format_output_data(
            df=df_tech_roadmap,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Technology roadmap",
            parameter="Technology roadmap",
            unit="Mt Clk",
        )

        # emission intensity clinker
        logger.info("-- Emission intensity")
        df_emission_intensity = _calculate_emissions_intensity(
            df_tech_roadmap=df_tech_roadmap,
            df_emissions=df_emissions.copy(),
            ghgs=GHGS,
            emission_scopes=EMISSION_SCOPES,
        )
        df_emission_intensity_formatted = _format_output_data(
            df=df_emission_intensity,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )

        # emission intensity cement & concrete
        df_emission_intensity_cmtcnt_formatted = _calculate_emissions_intensity_cmtcnt(
            importer=importer,
            df_emissions=df_emissions.copy(),
        )
        df_emission_intensity_cmtcnt_formatted = _format_output_data(
            df=df_emission_intensity_cmtcnt_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )

        # emissions
        logger.info("-- Emissions")
        df_emissions_formatted = _calculate_emissions_total(
            importer=importer,
            ghgs=GHGS,
            emission_scopes=EMISSION_SCOPES,
            format_data=True,
        )
        df_emissions_formatted = _format_output_data(
            df=df_emissions_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # emission abatement
        df_emission_abatement_formatted = _calculate_emission_reduction_levers(
            importer=importer,
            df_emissions=df_emissions.copy(),
            df_emission_intensity=df_emission_intensity.copy(),
            df_tech_roadmap=df_tech_roadmap,
        )
        df_emission_abatement_formatted = _format_output_data(
            df=df_emission_abatement_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Emissions abatement",
            parameter="CO2 Scope1&2",
            unit="Mt CO2",
        )
        # get captured carbon (incl. CC heat emissions)
        df_captured_carbon_formatted = (
            df_emissions.copy()
            .loc[(df_emissions["parameter"] == "co2_scope1_captured"), :]
            .set_index([x for x in df_emissions.columns if x != "value"])
            .groupby(
                [x for x in df_emissions.columns if x not in ["technology", "value"]]
            )
            .sum()
            .reset_index()
        )
        df_captured_carbon_formatted["technology"] = "All"
        df_captured_carbon_formatted = _format_output_data(
            df=df_captured_carbon_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Emissions",
            parameter="CO2 Scope1 captured",
            unit="Mt CO2",
        )
        # get carbon captured excl. CC heat emissions
        df_captured_emissions_excl_cc_process_formatted = (
            _get_captured_emissions_excl_cc_process_emissions(
                importer=importer,
                df_tech_roadmap=df_tech_roadmap,
            )
        )
        df_captured_emissions_excl_cc_process_formatted = _format_output_data(
            df=df_captured_emissions_excl_cc_process_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Emissions",
            parameter="CO2 Scope1 captured excl. CC heat emissions",
            unit="Mt CO2",
        )
        # get gross biomass captured emissions
        df_biomass_captured_carbon_formatted = _get_biomass_captured_emissions(
            importer=importer,
            df_resource_consumption_gj=df_resource_consumption_gj.copy(),
            df_resource_consumption_clkprod_only_gj=df_resource_consumption_clkprod_only_gj.copy(),
        )
        df_biomass_captured_carbon_formatted = _format_output_data(
            df=df_biomass_captured_carbon_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # get headline emissions for web interface
        idx = [
            "scenario",
            "sector",
            "product",
            "region",
            "technology",
            "parameter_group",
            "parameter",
            "unit",
        ]
        df_emissions_headline_excl_recarb_formatted = (
            df_emission_abatement_formatted.copy()
            .loc[
                df_emission_abatement_formatted["technology"].isin(
                    [
                        "Unabated Scope 1 emissions",
                        "Unabated Scope 2 emissions",
                        "Recarbonation",
                    ]
                ),
                :,
            ]
            .melt(
                id_vars=idx,
                value_vars=list(MODEL_YEARS),
            )
            .set_index(idx)
            .groupby([x for x in idx if x != "technology"] + ["year"])
            .sum()
            .reset_index()
            .pivot(
                index=[x for x in idx if x != "technology"],
                columns="year",
                values="value",
            )
            .reset_index()
        )
        df_emissions_headline_excl_recarb_formatted["technology"] = "All"
        df_emissions_headline_excl_recarb_formatted[
            "parameter_group"
        ] = "Headline emissions"
        df_emissions_headline_excl_recarb_formatted[
            "parameter"
        ] = "Annual emissions excl. recarbonation"
        df_emissions_headline_excl_recarb_formatted = (
            df_emissions_headline_excl_recarb_formatted[
                list(df_tech_roadmap_formatted.columns)
            ]
        )
        df_emissions_headline_incl_recarb_formatted = (
            df_emission_abatement_formatted.copy()
            .loc[
                df_emission_abatement_formatted["technology"].isin(
                    ["Unabated Scope 1 emissions", "Unabated Scope 2 emissions"]
                ),
                :,
            ]
            .melt(
                id_vars=idx,
                value_vars=list(MODEL_YEARS),
            )
            .set_index(idx)
            .groupby([x for x in idx if x != "technology"] + ["year"])
            .sum()
            .reset_index()
            .pivot(
                index=[x for x in idx if x != "technology"],
                columns="year",
                values="value",
            )
            .reset_index()
        )
        df_emissions_headline_incl_recarb_formatted["technology"] = "All"
        df_emissions_headline_incl_recarb_formatted[
            "parameter_group"
        ] = "Headline emissions"
        df_emissions_headline_incl_recarb_formatted[
            "parameter"
        ] = "Annual emissions incl. recarbonation"
        df_emissions_headline_incl_recarb_formatted = (
            df_emissions_headline_incl_recarb_formatted[
                list(df_tech_roadmap_formatted.columns)
            ]
        )

        # LCOC
        logger.info("-- Weighted average LCOC")
        df_weighted_average_lcoc_rel_formatted = _calculate_weighted_average_lcoc(
            df_cost=importer.get_technology_transitions_and_cost(),
            importer=importer,
        )
        df_weighted_average_lcoc_rel_formatted = (
            _calculate_weighted_average_lcoc_relative_change(
                df_weighted_average_lcoc=df_weighted_average_lcoc_rel_formatted
            )
        )
        # format
        df_weighted_average_lcoc_rel_formatted = _format_output_data(
            df=df_weighted_average_lcoc_rel_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Cost",
            parameter="LCOX",
            unit=f"% of {START_YEAR} value",
        )

        # Resource consumption
        logger.info("-- Resource consumption")
        # get energy consumption
        df_resource_consumption_pj_formatted = df_resource_consumption_gj.copy()
        # get alternative fuels (split into waste, biomass, and hydrogen)
        df_alternative_fuels_formatted = (
            df_resource_consumption_pj_formatted.copy().loc[
                df_resource_consumption_pj_formatted["parameter"].isin(
                    RESOURCE_CONSUMPTION_METRICS["Alternative fuels"]
                ),
                :,
            ]
        )
        df_alternative_fuels_formatted = (
            df_alternative_fuels_formatted.set_index(
                [x for x in df_alternative_fuels_formatted.columns if x != "value"]
            )
            .div(1e6)
            .reset_index()
        )
        # unit df_alternative_fuels_formatted: [PJ]
        df_alternative_fuels_formatted["parameter_group"] = "Alternative fuels"
        df_alternative_fuels_formatted["unit"] = "PJ"
        df_alternative_fuels_formatted = _format_output_data(
            df=df_alternative_fuels_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # get overall resource consumption in [PJ]
        df_total_resource_consumption_pj_formatted = (
            df_resource_consumption_pj_formatted.copy()
            .set_index(
                [
                    x
                    for x in df_resource_consumption_pj_formatted.columns
                    if x != "value"
                ]
            )
            .groupby(
                [
                    x
                    for x in df_resource_consumption_pj_formatted.columns
                    if x not in ["parameter", "value"]
                ]
            )
            .sum()
            .div(1e6)
            .reset_index()
        )
        # unit df_total_resource_consumption_pj_formatted: [PJ]
        df_total_resource_consumption_pj_formatted[
            "parameter"
        ] = "Total energy consumption"
        df_total_resource_consumption_pj_formatted["unit"] = "PJ"
        df_total_resource_consumption_pj_formatted = _format_output_data(
            df=df_total_resource_consumption_pj_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # convert resource consumption
        df_resource_consumption_formatted = _convert_resource_consumption(
            df_resource_consumption_pj_formatted.copy()
        )
        df_resource_consumption_pj_formatted = (
            df_resource_consumption_pj_formatted.set_index(
                [
                    x
                    for x in df_resource_consumption_pj_formatted.columns
                    if x != "value"
                ]
            )
            .div(1e6)
            .reset_index()
        )
        df_resource_consumption_pj_formatted["unit"] = "PJ"
        df_resource_consumption_pj_formatted = _format_output_data(
            df=df_resource_consumption_pj_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # Get resource consumption from clinker production only
        df_resource_consumption_clkprod_only_pj_formatted = (
            df_resource_consumption_clkprod_only_gj.copy()
        )
        # get overall resource consumption in [PJ]
        df_total_resource_consumption_clkprod_only_pj_formatted = (
            df_resource_consumption_clkprod_only_pj_formatted.copy()
            .set_index(
                [
                    x
                    for x in df_resource_consumption_clkprod_only_pj_formatted.columns
                    if x != "value"
                ]
            )
            .groupby(
                [
                    x
                    for x in df_resource_consumption_clkprod_only_pj_formatted.columns
                    if x not in ["parameter", "value"]
                ]
            )
            .sum()
            .div(1e6)
            .reset_index()
        )
        # unit df_total_resource_consumption_clkprod_only_pj_formatted: [PJ]
        df_total_resource_consumption_clkprod_only_pj_formatted[
            "parameter"
        ] = "Total energy consumption"
        df_total_resource_consumption_clkprod_only_pj_formatted["unit"] = "PJ"
        df_total_resource_consumption_clkprod_only_pj_formatted = _format_output_data(
            df=df_total_resource_consumption_clkprod_only_pj_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        # convert
        df_resource_consumption_clkprod_only_formatted = _convert_resource_consumption(
            df_resource_consumption_clkprod_only_pj_formatted.copy()
        )
        df_resource_consumption_clkprod_only_pj_formatted = (
            df_resource_consumption_clkprod_only_pj_formatted.set_index(
                [
                    x
                    for x in df_resource_consumption_clkprod_only_pj_formatted.columns
                    if x != "value"
                ]
            )
            .div(1e6)
            .reset_index()
        )
        df_resource_consumption_clkprod_only_pj_formatted["unit"] = "PJ"
        df_resource_consumption_clkprod_only_pj_formatted = _format_output_data(
            df=df_resource_consumption_clkprod_only_pj_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )
        df_resource_consumption_clkprod_only_formatted = _format_output_data(
            df=df_resource_consumption_clkprod_only_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )

        # format
        df_resource_consumption_formatted = _format_output_data(
            df=df_resource_consumption_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
        )

        # Number of net zero and initial plants
        df_number_plants_formatted = _get_number_plants_by_initial_net_zero(
            importer=importer, df_tech_roadmap=df_tech_roadmap
        )
        df_number_added_plants_formatted = _get_number_added_plants_by_initial_net_zero(
            df_number_plants=df_number_plants_formatted
        )
        df_number_plants_formatted = _format_output_data(
            df=df_number_plants_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Number of plants",
            parameter="Total plants",
            unit="abs",
        )
        df_number_added_plants_formatted = _format_output_data(
            df=df_number_added_plants_formatted,
            pathway_name=pathway_name,
            sensitivity=sensitivity,
            parameter_group="Number of plants",
            parameter="Annually added plants",
            unit="abs",
        )

        """ aggregate and export """
        logger.info("-- Aggregating outputs")
        df_aggregated_outputs_run = pd.concat(
            [
                df_tech_roadmap_formatted,
                df_emissions_formatted,
                df_captured_carbon_formatted,
                df_captured_emissions_excl_cc_process_formatted,
                df_emission_abatement_formatted,
                df_emissions_headline_incl_recarb_formatted,
                df_emissions_headline_excl_recarb_formatted,
                df_emission_intensity_formatted,
                df_emission_intensity_cmtcnt_formatted,
                df_biomass_captured_carbon_formatted,
                df_weighted_average_lcoc_rel_formatted,
                df_resource_consumption_pj_formatted,
                df_resource_consumption_formatted,
                df_total_resource_consumption_pj_formatted,
                df_resource_consumption_clkprod_only_pj_formatted,
                df_resource_consumption_clkprod_only_formatted,
                df_total_resource_consumption_clkprod_only_pj_formatted,
                df_alternative_fuels_formatted,
                df_number_plants_formatted,
                df_number_added_plants_formatted,
            ]
        )
        df_list.append(df_aggregated_outputs_run.fillna(float(0)))

    logger.info("Export")
    # aggregate
    df_aggregated_outputs = pd.concat(df_list)
    # export
    export_path = (
        f"{Path(__file__).resolve().parents[2]}/{sector}/data/aggregated_outputs.csv"
    )
    df_aggregated_outputs.to_csv(export_path, index=False)


def calculate_outputs(sector: str, products: list, pathway_name: str, sensitivity: str):

    importer = IntermediateDataImporter(
        pathway_name=pathway_name,
        sensitivity=sensitivity,
        sector=sector,
        products=PRODUCTS,
    )

    """ technology roadmap """
    logger.info("Post-processing technology roadmap")
    # get roadmap
    df_tech_roadmap = _create_tech_roadmaps_by_region(
        importer=importer, start_year=START_YEAR, end_year=END_YEAR
    )
    # export & plot
    _export_and_plot_tech_roadmaps_by_region(
        pathway_name=pathway_name,
        sensitivity=sensitivity,
        importer=importer,
        df_roadmap=df_tech_roadmap,
        unit="Mt Clk",
        technology_layout=TECHNOLOGY_LAYOUT,
    )

    """ Emissions """
    logger.info("Post-processing emissions")
    # get emissions
    df_emissions = _calculate_emissions_total(
        importer=importer,
        ghgs=GHGS,
        emission_scopes=EMISSION_SCOPES,
        format_data=False,
    )
    # export and plot
    _export_and_plot_emissions_by_region(
        pathway_name=pathway_name,
        sensitivity=sensitivity,
        importer=importer,
        df_emissions=df_emissions,
        ghgs=GHGS,
        emission_scopes=EMISSION_SCOPES,
        technology_layout=TECHNOLOGY_LAYOUT,
    )

    """ Emission intensity """
    # get emission intensity
    df_emission_intensity = _calculate_emissions_intensity(
        df_tech_roadmap=df_tech_roadmap,
        df_emissions=df_emissions,
        ghgs=GHGS,
        emission_scopes=EMISSION_SCOPES,
    )
    # export
    importer.export_data(
        df=df_emission_intensity,
        filename=f"{pathway_name}_emission_intensity.csv",
        export_dir="final/emissions",
        index=True,
    )

    """ Number of plants """
    logger.info("Post-processing number of plants")
    df_number_plants = _get_number_plants_by_initial_net_zero(
        importer=importer, df_tech_roadmap=df_tech_roadmap
    )
    importer.export_data(
        df=df_number_plants,
        filename=f"{pathway_name}_number_of_plants.csv",
        export_dir="final",
        index=True,
    )

    """ LCOC """
    # get weighted average LCOC
    df_weighted_average_lcoc = _calculate_weighted_average_lcoc(
        df_cost=importer.get_technology_transitions_and_cost(),
        importer=importer,
    )
    # export pivoted LCOC
    _export_greenfield_lcoc(importer=importer, pathway_name=pathway_name)
    # export and plot
    _export_and_plot_weighted_average_lcox_by_region(
        pathway_name=pathway_name,
        sensitivity=sensitivity,
        importer=importer,
        df_weighted_average_lcox=df_weighted_average_lcoc,
        unit="USD/t Clk",
        technology_layout=TECHNOLOGY_LAYOUT,
    )

    """ resource consumption """
    logger.info("Post-processing resource consumption")
    df_resource_consumption = _calculate_resource_consumption_gj(importer=importer)
    _export_and_plot_resource_consumption(
        pathway_name=pathway_name,
        sensitivity=sensitivity,
        importer=importer,
        df_resource_consumption=df_resource_consumption,
        unit="GJ",
    )

    logger.info("Output processing done")


""" technology roadmap """


def _create_tech_roadmaps_by_region(
    importer: IntermediateDataImporter,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """
    Annual production volume in Mt production_output by technology and region

    Args:
        importer ():
        start_year ():
        end_year ():

    Returns:
        df_stack (Unit: [Mt Clk])
    """

    idx = ["product", "year", "region", "technology"]

    # region
    df_list = []
    for year in np.arange(start_year, end_year + 1):
        # Group by technology and sum annual production volume
        df_stack = importer.get_asset_stack(year=year)
        df_stack = df_stack[["region", "technology", "annual_production_volume"]]
        df_stack = df_stack.groupby(["region", "technology"]).sum().reset_index()
        df_stack["year"] = year
        df_stack["product"] = PRODUCTS[0]
        df_stack = df_stack.set_index(idx).sort_index()
        # add to df_list
        df_list.append(df_stack)
    df_stack = pd.concat(df_list)

    # global
    df_stack_global = df_stack.groupby(["year", "technology"]).sum()
    df_stack_global["region"] = "Global"
    df_stack_global["product"] = PRODUCTS[0]
    df_stack_global = df_stack_global.reset_index().set_index(idx)

    df_stack = pd.concat([df_stack, df_stack_global]).sort_index().reset_index()

    df_stack.rename(columns={"annual_production_volume": "value"}, inplace=True)

    return df_stack


def _export_and_plot_tech_roadmaps_by_region(
    pathway_name: str,
    sensitivity: str,
    importer: IntermediateDataImporter,
    df_roadmap: pd.DataFrame,
    unit: str,
    technology_layout: dict,
):

    regions = df_roadmap.reset_index()["region"].unique()

    for region in regions:
        df_roadmap_region = df_roadmap.loc[(df_roadmap["region"] == region), :]

        importer.export_data(
            df=df_roadmap_region,
            filename=f"{pathway_name}_technology_roadmap_{region}.csv",
            export_dir="final/technology_roadmap",
            index=False,
        )

        fig = px.area(
            data_frame=df_roadmap_region,
            x="year",
            y="value",
            color="technology",
            labels={
                "year": "Year",
                "value": f"Annual production volume in {unit}",
            },
            title=f"{region}: Technology roadmap ({pathway_name}_{sensitivity})",
            category_orders={"technology": list(technology_layout)},
            color_discrete_map=technology_layout,
        )

        fig.for_each_trace(lambda trace: trace.update(fillcolor=trace.line.color))

        plot(
            figure_or_data=fig,
            filename=f"{importer.final_path}/technology_roadmap/{pathway_name}_technology_roadmap_{region}.html",
            auto_open=False,
        )

        # get global tech shares
        if region == "Global":
            fig = px.area(
                data_frame=df_roadmap_region,
                x="year",
                y="value",
                color="technology",
                labels={
                    "year": "Year",
                    "value": f"Annual production volume in %",
                },
                title=f"{region}: Technology roadmap shares ({pathway_name}_{sensitivity})",
                category_orders={"technology": list(technology_layout)},
                color_discrete_map=technology_layout,
                groupnorm="percent",
            )

            fig.for_each_trace(lambda trace: trace.update(fillcolor=trace.line.color))

            plot(
                figure_or_data=fig,
                filename=(
                    f"{importer.final_path}/technology_roadmap/{pathway_name}_technology_roadmap_{region}_shares.html"
                ),
                auto_open=False,
            )


""" Emissions """


def _calculate_emissions_year(
    importer: IntermediateDataImporter,
    year: int,
    ghgs: list = GHGS,
    emission_scopes: list = EMISSION_SCOPES,
) -> pd.DataFrame:
    """Calculate emissions in Mt GHG for all GHGs and scopes by production, region and technology"""

    idx = ["product", "region", "technology"]

    df_emissions = importer.get_emissions()
    df_emissions = df_emissions.loc[df_emissions["year"] == year, :].drop(
        columns="year"
    )
    df_stack = importer.get_asset_stack(year=year)

    # Emissions are the emissions factor multiplied with the annual production volume

    df_stack = df_stack.merge(df_emissions, on=idx)
    scopes = [f"{ghg}_{scope}" for scope in emission_scopes for ghg in ghgs]

    for scope in scopes:
        df_stack[scope] = df_stack[scope] * df_stack["annual_production_volume"]

    df_stack = (
        df_stack.groupby(idx)[scopes + ["annual_production_volume"]].sum().reset_index()
    )

    # global
    df_stack_global = (
        df_stack.copy().set_index(idx).groupby(["product", "technology"]).sum()
    )
    df_stack_global["region"] = "Global"
    df_stack_global = df_stack_global.reset_index()
    df_stack = pd.concat(objs=[df_stack, df_stack_global], axis=0)

    df_stack = df_stack.melt(
        id_vars=idx,
        value_vars=scopes,
        var_name="parameter",
        value_name="value",
    )

    return df_stack


def _calculate_co2_captured(
    importer: IntermediateDataImporter,
    year: int,
) -> pd.DataFrame:
    """Calculate captured CO2 by product, region and technology for a given asset stack"""

    idx = ["product", "region", "technology"]

    df_emissions = importer.get_emissions()
    df_emissions = df_emissions.loc[df_emissions["year"] == year, :].drop(
        columns="year"
    )
    df_stack = importer.get_asset_stack(year=year)

    # Captured CO2 by technology is calculated by multiplying with the annual production volume
    df_stack = df_stack.merge(df_emissions, on=idx)
    df_stack["co2_scope1_captured"] = (
        -df_stack["co2_scope1_captured"] * df_stack["annual_production_volume"]
    )

    df_stack = df_stack.groupby(idx)["co2_scope1_captured"].sum().reset_index()

    # global
    df_stack_global = (
        df_stack.copy().set_index(idx).groupby(["product", "technology"]).sum()
    )
    df_stack_global["region"] = "Global"
    df_stack_global = df_stack_global.reset_index()
    df_stack = pd.concat(objs=[df_stack, df_stack_global], axis=0)

    # Melt and add parameter descriptions
    df_stack = df_stack.melt(
        id_vars=idx,
        value_vars="co2_scope1_captured",
        var_name="parameter",
        value_name="value",
    )

    return df_stack


def _calculate_emissions_total(
    importer: IntermediateDataImporter,
    ghgs: list = GHGS,
    emission_scopes: list = EMISSION_SCOPES,
    format_data: bool = True,
) -> pd.DataFrame:
    """Calculates the emissions of the entire model horizon"""

    df_list = []
    for year in MODEL_YEARS:
        df_emissions = _calculate_emissions_year(
            importer=importer,
            year=year,
            ghgs=ghgs,
            emission_scopes=emission_scopes,
        )
        df_captured_emissions = _calculate_co2_captured(
            importer=importer,
            year=year,
        )
        df_emissions["year"] = year
        df_captured_emissions["year"] = year
        df_list.append(df_emissions)
        df_list.append(df_captured_emissions)

    df = pd.concat(objs=df_list, axis=0)

    cols = ["year"] + [x for x in df.columns if x != "year"]
    df = df[cols]

    df = df.sort_values(
        ["year", "product", "region", "technology", "parameter"]
    ).reset_index(drop=True)

    if format_data:
        # Add unit and parameter group
        map_unit = {
            f"{ghg}_{scope}": f"Mt {str.upper(ghg)}"
            for scope in emission_scopes + ["scope1_captured"]
            for ghg in ghgs
        }
        map_rename = {
            f"{ghg}_{scope}": f"{str.upper(ghg)} {str.capitalize(scope).replace('_', ' ')}"
            for scope in emission_scopes + ["scope1_captured"]
            for ghg in ghgs
        }

        df["parameter_group"] = "Emissions"
        df["unit"] = df["parameter"].apply(lambda x: map_unit[x])
        df["parameter"] = df["parameter"].replace(map_rename)

    return df


def _export_and_plot_emissions_by_region(
    pathway_name: str,
    sensitivity: str,
    importer: IntermediateDataImporter,
    df_emissions: pd.DataFrame,
    ghgs: list = GHGS,
    emission_scopes: list = EMISSION_SCOPES,
    technology_layout: dict = TECHNOLOGY_LAYOUT,
):

    regions = df_emissions["region"].unique()

    for region in regions:
        df_region = df_emissions.copy().loc[df_emissions["region"] == region, :]

        importer.export_data(
            df=df_region,
            filename=f"{pathway_name}_emissions_{region}.csv",
            export_dir="final/emissions",
            index=False,
        )

        # area plots
        for ghg in ghgs:

            df_region_area = df_region.copy().loc[
                df_region["parameter"].isin([f"{ghg}_{x}" for x in emission_scopes]), :
            ]
            df_region_area = (
                df_region_area.set_index(
                    [x for x in df_region_area.columns if x != "value"]
                )
                .groupby(["year", "technology"])
                .sum()
                .reset_index()
            )

            cum_sum = np.round(a=df_region_area["value"].sum() / 1e3, decimals=2)
            cum_scopes12_sum = np.round(
                a=df_region.copy()
                .loc[
                    df_region["parameter"].isin(
                        [f"{ghg}_{x}" for x in ["scope1", "scope2"]]
                    ),
                    "value",
                ]
                .sum()
                / 1e3,
                decimals=2,
            )
            fig_area = px.area(
                data_frame=df_region_area,
                x="year",
                y="value",
                color="technology",
                labels={
                    "year": "Year",
                    "value": f"{ghg} emissions in Mt {ghg}",
                },
                title=(
                    f"{region}: {ghg} emissions all scopes ({pathway_name}_{sensitivity} "
                    f"| cum.: {cum_sum} Gt {ghg} "
                    f"| cum. scopes 1 & 2: {cum_scopes12_sum} Gt {ghg})"
                ),
                category_orders={"technology": list(technology_layout)},
                color_discrete_map=technology_layout,
            )

            fig_area.for_each_trace(
                lambda trace: trace.update(fillcolor=trace.line.color)
            )

            plot(
                figure_or_data=fig_area,
                filename=f"{importer.final_path}/emissions/{pathway_name}_emissions_by_tech_{region}_{ghg}.html",
                auto_open=False,
            )

        # line plots
        df_region_line = (
            df_region.copy()
            .set_index([x for x in df_region.columns if x != "value"])
            .groupby(["year", "parameter"])
            .sum()
            .reset_index()
        )
        # add total emissions over all scopes
        df_list = []
        for ghg in ghgs:
            df_region_line_all_scopes = df_region_line.copy().loc[
                df_region_line["parameter"].isin(
                    [f"{ghg}_{x}" for x in emission_scopes]
                ),
                :,
            ]
            df_region_line_all_scopes = (
                df_region_line_all_scopes.set_index(
                    [
                        x
                        for x in df_region_line_all_scopes.columns
                        if x not in ["value", "co2_scope1_captured"]
                    ]
                )
                .groupby(["year"])
                .sum()
                .reset_index()
            )
            df_region_line_all_scopes["parameter"] = f"{ghg}_all-scopes"
            df_list.append(df_region_line_all_scopes)
        df_region_line = pd.concat(objs=[df_region_line] + df_list, axis=0)
        fig_line = px.line(
            data_frame=df_region_line,
            x="year",
            y="value",
            color="parameter",
            labels={
                "year": "Year",
                "value": f"Emissions in Mt GHG",
            },
            title=f"{region}: Emissions by GHG and scope ({pathway_name}_{sensitivity})",
            category_orders={"technology": list(technology_layout)},
            color_discrete_map=technology_layout,
        )

        plot(
            figure_or_data=fig_line,
            filename=f"{importer.final_path}/emissions/{pathway_name}_emissions_by_ghg_scope_{region}.html",
            auto_open=False,
        )


def _calculate_emission_reduction_levers(
    importer: IntermediateDataImporter,
    df_tech_roadmap: pd.DataFrame,
    df_emissions: pd.DataFrame,
    df_emission_intensity: pd.DataFrame,
) -> pd.DataFrame:
    """Calculates the levers
            - "Savings through CCU/S"
            - "Switching to alternative fuels and energy efficiency" and
            - "Recarbonation" (negative numbers such that it shows below other levers)
        and pulls the levers
            - three demand reduction levers from Demand Excel model
            - "Decarbonisation of electricity"
            - "Unabated Scope 2 emissions"
        from the Demand Excel model outputs and adds them all to df_outputs_demand_model

    Args:
        importer ():
        df_tech_roadmap (): [Mt Clk]
        df_emissions (): [Mt GHG]

    Returns:

    """

    # import demand reduction levers
    df_outputs_demand_model = importer.get_outputs_demand_model()
    df_outputs_demand_model["product"] = PRODUCTS[0]
    # Unit df_outputs_demand_model: [Mt CO2] / [Mt Cnt] / [Mt Cmt] / [GJ]

    """ compute recarbonation = production volume * recarbonation share """

    df_recarbonation = df_tech_roadmap.copy().loc[
        (df_tech_roadmap["region"] == "Global"), :
    ]
    df_recarbonation.set_index(
        keys=[x for x in df_recarbonation.columns if x != "value"], inplace=True
    )
    df_recarbonation = df_recarbonation.groupby(
        [x for x in df_recarbonation.index.names if x != "technology"]
    ).sum()
    df_recarbonation *= RECARBONATION_SHARE

    """ compute Switching to alternative fuels and energy efficiency """

    # get unabated scope 1 emissions
    df_emissions = df_emissions.copy().loc[(df_emissions["region"] == "Global"), :]
    df_unabated_s1_emissions = df_emissions.copy().loc[
        (df_emissions["parameter"] == "co2_scope1"),
        ["year", "product", "region", "value"],
    ]
    df_unabated_s1_emissions.set_index(
        keys=[x for x in df_unabated_s1_emissions.columns if x != "value"],
        inplace=True,
    )
    df_unabated_s1_emissions = (
        df_unabated_s1_emissions.groupby(["year", "product", "region"])
        .sum()
        .sort_index()
    )

    # get unabated scope 2 emissions
    # unabated clinker scope 2
    df_unabated_s2_emissions = df_emissions.copy().loc[
        (df_emissions["parameter"] == "co2_scope2"),
        ["year", "product", "region", "value"],
    ]
    df_unabated_s2_emissions.set_index(
        keys=[x for x in df_unabated_s2_emissions.columns if x != "value"],
        inplace=True,
    )
    df_unabated_s2_emissions = df_unabated_s2_emissions.groupby(
        ["year", "product", "region"]
    ).sum()
    # unabated cement & concrete scope 2
    df_unabated_cmtcnt_s2_emissions = df_outputs_demand_model.copy().loc[
        (
            df_outputs_demand_model["technology"].isin(
                ["Cement scope 2 emissions", "Concrete scope 2 emissions"]
            )
        ),
        ["year", "product", "region", "value"],
    ]
    df_unabated_cmtcnt_s2_emissions.set_index(
        keys=[x for x in df_unabated_cmtcnt_s2_emissions.columns if x != "value"],
        inplace=True,
    )
    df_unabated_cmtcnt_s2_emissions = df_unabated_cmtcnt_s2_emissions.groupby(
        ["year", "product", "region"]
    ).sum()
    # sum
    df_unabated_s2_emissions += df_unabated_cmtcnt_s2_emissions

    # get unabated clinker emissions before CCU/S and switch to AF and slightly adjust them to exactly match the 2020
    #   in the outputs of this model
    df_unabated_s1_emissions_pre_clinker_levers = (
        _get_unabated_s1_emissions_pre_clinker_levers(
            df_emission_intensity=df_emission_intensity.copy(),
            df_tech_roadmap=df_tech_roadmap,
        )
    )

    # get savings in clinker production (fuel switch and energy efficiency)
    df_fuel_switch, df_energy_eff = _get_savings_in_clinker_production(
        importer=importer,
        df_tech_roadmap=df_tech_roadmap,
    )
    df_fuel_switch.sort_index(inplace=True)
    df_energy_eff.sort_index(inplace=True)

    # get emission reduction through CCU/S
    df_savings_captured_emissions = (
        df_unabated_s1_emissions_pre_clinker_levers.copy()
        - df_unabated_s1_emissions
        - df_fuel_switch
        - df_energy_eff
    ).sort_index()

    # potential negative values in df_savings_captured_emissions come from inaccuracies in df_fuel_switch. Correct them:
    df_fuel_switch.loc[(df_savings_captured_emissions["value"] < 0), "value"] = (
        (
            df_unabated_s1_emissions_pre_clinker_levers.copy()
            - df_unabated_s1_emissions
            - df_energy_eff
        )
        .sort_index()
        .loc[(df_savings_captured_emissions["value"] < 0), "value"]
    )
    df_savings_captured_emissions = (
        df_unabated_s1_emissions_pre_clinker_levers.copy()
        - df_unabated_s1_emissions
        - df_fuel_switch
        - df_energy_eff
    ).sort_index()

    # aggregate df_fuel_switch and df_energy_eff
    df_savings_clinker_production = df_fuel_switch.add(df_energy_eff)

    # reduce unabated scope 1 emissions by recarbonation
    df_unabated_s1_emissions -= df_recarbonation

    """ pull data for the three demand reduction levers as well as "Decarbonisation of electricity" """

    df_demand_excel_levers = df_outputs_demand_model.copy().loc[
        df_outputs_demand_model["technology"].isin(
            [
                "Efficiency in design and construction",
                "Efficiency in concrete production",
                "Savings in cement (incl. new binders & calcined clay emissions)",
                "Decarbonisation of electricity",
            ]
        ),
        ["product", "year", "region", "value", "technology"],
    ]

    # aggregate
    df_savings_clinker_production[
        "technology"
    ] = "Switching to alternative fuels and thermal efficiency"
    df_savings_captured_emissions["technology"] = "Savings through CCU/S"
    df_unabated_s1_emissions["technology"] = "Unabated Scope 1 emissions"
    df_unabated_s2_emissions["technology"] = "Unabated Scope 2 emissions"
    df_recarbonation["technology"] = "Recarbonation"

    df = pd.concat(
        [
            df_demand_excel_levers,
            df_savings_clinker_production.reset_index(),
            df_savings_captured_emissions.reset_index(),
            df_unabated_s1_emissions.reset_index(),
            df_unabated_s2_emissions.reset_index(),
            df_recarbonation.reset_index(),
        ]
    ).reset_index(drop=True)

    return df


def _get_savings_in_clinker_production(
    importer: IntermediateDataImporter,
    df_tech_roadmap: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculates the savings in clinker production (i.e., the savings coming from fuel switch and efficiency gains). The
        savings are calculated based on the change in weighted average emission factor before carbon capturing.

    Args:
        importer ():
        df_tech_roadmap ():

    Returns:
        df_energy_eff (): savings through energy efficiency
        df_fuel_switch (): savings through fuel switch
    """

    idx = ["product", "year", "region"]
    df_emissions = importer.get_emissions().loc[:, idx + ["technology", "co2_scope1"]]
    df_tech_emission_factors = df_emissions.copy()

    # get the emission factors for carbon capture setups that they would have without carbon capture
    df_tech_emission_factors["value"] = df_tech_emission_factors.apply(
        lambda x: _get_emission_factor_pre_capture(
            row=x,
            importer=importer,
            df_emissions=df_emissions,
            value_if_none=x.loc["co2_scope1"],
        ),
        axis=1,
    )
    df_tech_emission_factors = df_tech_emission_factors[
        idx + ["technology", "value"]
    ].set_index(keys=(idx + ["technology"]))

    df_tech_roadmap = (
        df_tech_roadmap.copy()
        .loc[(df_tech_roadmap["region"] != "Global"), :]
        .set_index(keys=(idx + ["technology"]))
    )

    """ get carbon savings through energy efficiency """
    # calculate energy efficiency savings as difference in emission factor to START_YEAR per region and technology
    def _get_reduction_to_start_year(sub_df: pd.DataFrame):
        start = sub_df.xs(key=START_YEAR, level="year").squeeze()
        sub_df = start - sub_df
        return sub_df

    df_tech_emission_factors_eff = (
        df_tech_emission_factors.copy()
        .groupby(([x for x in idx if x != "year"] + ["technology"]))
        .apply(lambda x: _get_reduction_to_start_year(x))
    )

    # multiply with tech roadmap
    df_energy_eff = (
        df_tech_roadmap.copy().mul(df_tech_emission_factors_eff).dropna(how="all")
    )

    # aggregate technologies
    df_energy_eff = df_energy_eff.groupby(
        [x for x in df_energy_eff.index.names if x != "technology"]
    ).sum()

    """ 
        get savings through fuel switch as difference in average emission factor over the years weighted by technology
        deployment (energy efficiency gains are excluded by assuming using only emission factors from START_YEAR)
    """

    # get emissions by region and year and derive respective emission factors
    df_tech_emission_factors_start_year = df_tech_emission_factors.copy().xs(
        key=START_YEAR, level="year"
    )
    # compute weighted average emission factor
    df_fuel_switch = (
        df_tech_roadmap.mul(df_tech_emission_factors_start_year)
        .reorder_levels((idx + ["technology"]))
        .dropna(how="all")
    )
    df_fuel_switch = (
        df_fuel_switch.div(
            df_tech_roadmap.groupby(
                [x for x in df_tech_roadmap.index.names if x != "technology"]
            ).sum()
        )
        .groupby(idx)
        .sum()
        .reorder_levels(idx)
        .sort_index()
    )
    # per region: get reduction due to fuel switch
    df_fuel_switch = df_fuel_switch.groupby([x for x in idx if x != "year"]).apply(
        lambda x: _get_reduction_to_start_year(x)
    )
    # get emission savings through fuel switch
    df_fuel_switch = df_fuel_switch.mul(
        df_tech_roadmap.groupby(
            [x for x in df_tech_roadmap.index.names if x != "technology"]
        ).sum()
    )

    """ aggregate to global """
    df_fuel_switch = df_fuel_switch.groupby(
        [x for x in df_fuel_switch.index.names if x not in ["region", "technology"]]
    ).sum()
    df_fuel_switch["region"] = "Global"
    df_fuel_switch = df_fuel_switch.reset_index().set_index(idx).sort_index()
    df_energy_eff = df_energy_eff.groupby(
        [x for x in df_energy_eff.index.names if x not in ["region", "technology"]]
    ).sum()
    df_energy_eff["region"] = "Global"
    df_energy_eff = df_energy_eff.reset_index().set_index(idx).sort_index()

    return df_fuel_switch, df_energy_eff


def _get_captured_emissions_excl_cc_process_emissions(
    importer: IntermediateDataImporter,
    df_tech_roadmap: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculates the emissions from clinker production that are being captured without carbon capture process emissions

    Args:
        importer ():

    Returns:

    """

    idx = ["product", "year", "region", "technology"]
    df_emissions = importer.get_emissions().loc[:, idx + ["co2_scope1"]]
    df_tech_emission_factors = df_emissions.copy()
    df_capture_rate = importer.get_imported_input_data(
        input_metrics={"Technology cards": ["capture_rate"]}
    )["capture_rate"]

    # get the emission factors for carbon capture setups that they would have without carbon capture
    df_tech_emission_factors["value"] = df_tech_emission_factors.apply(
        lambda x: _get_emission_factor_pre_capture(
            row=x, importer=importer, df_emissions=df_emissions, value_if_none=float(0)
        ),
        axis=1,
    )
    df_tech_emission_factors = df_tech_emission_factors[idx + ["value"]].set_index(idx)

    # multiply with capture rate
    df_capture_rate.rename(
        columns={"technology_destination": "technology"}, inplace=True
    )
    df_capture_rate = df_capture_rate[idx + ["value"]].set_index(idx)
    df_tech_emission_factors *= df_capture_rate

    # multiply with tech roadmap to get saved emissions through CCU/S in Mt CO2
    df = (
        df_tech_roadmap.copy()
        .loc[(df_tech_roadmap["region"] != "Global"), :]
        .set_index(idx)
    )
    df = df.mul(df_tech_emission_factors).dropna(how="all")

    # aggregate
    df = df.groupby([x for x in idx if x not in ["region", "technology"]]).sum()
    df["region"] = "Global"
    df["technology"] = "All"
    df = df.reset_index().set_index(idx).sort_index().reset_index()

    return df


def _get_unabated_s1_emissions_pre_clinker_levers(
    df_emission_intensity: pd.DataFrame,
    df_tech_roadmap: pd.DataFrame,
) -> pd.DataFrame:
    """
    Computes the emissions that clinker production would have if the global emission factor stays on START_YEAR level

    Args:
        df_emission_intensity ():
        df_tech_roadmap ():

    Returns:

    """

    idx = ["product", "year", "region"]

    df_tech_roadmap = (
        df_tech_roadmap.copy()
        .loc[(df_tech_roadmap["region"] == "Global"), :]
        .set_index(keys=(idx + ["technology"]))
        .groupby(idx)
        .sum()
    )

    # get emission intensity in start year
    emission_intensity_start_year = (
        df_emission_intensity.copy()
        .loc[
            (
                (df_emission_intensity["region"] == "Global")
                & (df_emission_intensity["year"] == START_YEAR)
                & (
                    df_emission_intensity["parameter"]
                    == "Emissions intensity CO2E Scope1"
                )
            ),
            "value",
        ]
        .squeeze()
    )

    # get emissions
    df = df_tech_roadmap.mul(emission_intensity_start_year).reorder_levels(idx)

    return df


def _get_biomass_captured_emissions(
    importer: IntermediateDataImporter,
    df_resource_consumption_gj: pd.DataFrame,
    df_resource_consumption_clkprod_only_gj: pd.DataFrame,
) -> pd.DataFrame:
    """
    Computes the gross biomass emissions that might be captured, including the respective CC heat emissions

    Args:
        importer ():
        df_resource_consumption_gj ():

    Returns:

    """

    idx = ["product", "year", "region"]

    df_gross_bio_emission_factor = importer.get_imported_input_data(
        input_metrics={"Shared inputs - Emissivity": ["emissivity_co2"]}
    )["emissivity_co2"]
    df_gross_bio_emission_factor = df_gross_bio_emission_factor.loc[
        df_gross_bio_emission_factor["metric"].str.contains("Biomass"),
        ["product", "year", "region", "value"],
    ]
    df_gross_bio_emission_factor.set_index(keys=idx, inplace=True)

    # remaining emissions = gross emissions - net emissions
    df_gross_bio_emission_factor = (
        GROSS_BIO_EMISSION_FACTOR - df_gross_bio_emission_factor
    )

    # multiply with capture rate
    df_gross_bio_emission_factor *= ASSUMED_CARBON_CAPTURE_RATE

    # total emissions #
    df_resource_consumption_gj = (
        df_resource_consumption_gj.copy()
        .loc[
            (
                (df_resource_consumption_gj["parameter"].str.contains("Biomass"))
                & (df_resource_consumption_gj["region"] != "Global")
            ),
            (idx + ["value"]),
        ]
        .set_index(keys=idx)
    )
    df_total = df_gross_bio_emission_factor.mul(df_resource_consumption_gj)
    # aggregate to global
    df_total_global = df_total.groupby([x for x in idx if x != "region"]).sum()
    df_total_global["region"] = "Global"
    df_total_global = df_total_global.reset_index().set_index(keys=idx)
    # concat
    df_total = pd.concat([df_total, df_total_global]).sort_index().div(1e6)
    df_total["technology"] = "All"
    df_total = df_total.reset_index().set_index(keys=(idx + ["technology"]))

    # heat emissions #
    df_resource_consumption_clkprod_only_gj = (
        df_resource_consumption_clkprod_only_gj.copy()
        .loc[
            (
                (
                    df_resource_consumption_clkprod_only_gj["parameter"].str.contains(
                        "Biomass"
                    )
                )
                & (df_resource_consumption_clkprod_only_gj["region"] != "Global")
            ),
            (idx + ["value"]),
        ]
        .set_index(keys=idx)
    )
    df_heat = df_gross_bio_emission_factor.mul(df_resource_consumption_clkprod_only_gj)
    # aggregate to global
    df_heat_global = df_heat.groupby([x for x in idx if x != "region"]).sum()
    df_heat_global["region"] = "Global"
    df_heat_global = df_heat_global.reset_index().set_index(keys=idx)
    # concat
    df_heat = pd.concat([df_heat, df_heat_global]).sort_index().div(1e6)
    df_heat["technology"] = "All"
    df_heat = df_heat.reset_index().set_index(keys=(idx + ["technology"]))

    # CC heat emissions
    df_cc_heat = df_total.sub(df_heat)

    # set parameter and aggregate
    df_total["parameter_group"] = "Emissions"
    df_total["parameter"] = "Captured gross biomass emissions"
    df_total["unit"] = "Mt CO2"
    df_heat["parameter_group"] = "Emissions"
    df_heat["parameter"] = "Captured gross biomass emissions (Clinker production only)"
    df_heat["unit"] = "Mt CO2"
    df_cc_heat["parameter_group"] = "Emissions"
    df_cc_heat["parameter"] = "Captured gross biomass emissions (CC heat only)"
    df_cc_heat["unit"] = "Mt CO2"
    df = pd.concat(
        [
            df_total.reset_index(),
            df_heat.reset_index(),
            df_cc_heat.reset_index(),
        ]
    )

    return df


""" Emission intensity """


def _calculate_emissions_intensity(
    df_tech_roadmap: pd.DataFrame,
    df_emissions: pd.DataFrame,
    ghgs: list = GHGS,
    emission_scopes: list = EMISSION_SCOPES,
) -> pd.DataFrame:
    """
    Calculate emissions intensity [t GHG / t production_output] for a given stack

    Args:
        df_tech_roadmap (): [Mt production_output]
        df_emissions (): [Mt GHG]

    Returns:

    """

    logger.info("-- Calculating emissions intensity")

    agg_vars = ["product", "region"]

    df_emissions = df_emissions.copy().rename(columns={"value": "emissions"})
    # remove captured emissions
    df_emissions = df_emissions.loc[
        ~df_emissions["parameter"].str.contains("captured"), :
    ]
    # add total emissions over all scopes
    df_list = []
    for ghg in ghgs:
        df_scopes12 = df_emissions.copy().loc[
            df_emissions["parameter"].isin(
                [f"{ghg}_{x}" for x in emission_scopes if x in ["scope1", "scope2"]]
            ),
            :,
        ]
        df_scopes12 = (
            df_scopes12.set_index([x for x in df_scopes12.columns if x != "emissions"])
            .groupby(["product", "year", "region", "technology"])
            .sum()
            .reset_index()
        )
        df_scopes12["parameter"] = f"{ghg}_scopes1&2"
        df_list.append(df_scopes12)
    df_emissions = pd.concat(objs=[df_emissions] + df_list, axis=0)

    # aggregate
    df_emission_intensity = df_tech_roadmap.merge(
        df_emissions, on=["product", "year", "region", "technology"]
    )
    df_emission_intensity = (
        df_emission_intensity.groupby(["product", "year", "region", "parameter"])
        .sum()
        .reset_index()
    )

    df_emission_intensity["value"] = (
        df_emission_intensity["emissions"] / df_emission_intensity["value"]
    )

    df_emission_intensity.drop(columns="emissions", inplace=True)

    # Add unit and parameter group
    map_unit = {
        f"{ghg}_{scope}": f"t{str.upper(ghg)}/t"
        for scope in EMISSION_SCOPES + ["scopes1&2"]
        for ghg in GHGS
    }
    map_rename = {
        f"{ghg}_{scope}": f"Emissions intensity {str.upper(ghg)} {str.capitalize(scope).replace('_', ' ')}"
        for scope in EMISSION_SCOPES + ["scopes1&2"]
        for ghg in GHGS
    }

    df_emission_intensity["parameter_group"] = "Emissions intensity"
    df_emission_intensity["unit"] = df_emission_intensity["parameter"].apply(
        lambda x: map_unit[x]
    )
    df_emission_intensity["parameter"] = df_emission_intensity["parameter"].replace(
        map_rename
    )
    if "technology" not in agg_vars:
        df_emission_intensity["technology"] = "All"

    return df_emission_intensity


def _calculate_emissions_intensity_cmtcnt(
    importer: IntermediateDataImporter,
    df_emissions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculates the emissions intensities for cement and concrete for scopes 1 and 2

    Args:
        importer ():
        df_emissions ():

    Returns:
        df (): Unit: [t CO2 / t cmt] / [t CO2 / t cnt]
    """

    idx = ["product", "year", "region"]

    # import demand reduction levers
    df_outputs_demand_model = importer.get_outputs_demand_model()
    df_outputs_demand_model["product"] = PRODUCTS[0]
    # Unit df_outputs_demand_model: [Mt CO2] / [Mt Cnt] / [Mt Cmt] / [GJ]

    # get clinker scope 1 emissions
    df_emissions_clinker_scope1 = df_emissions.copy().loc[
        (
            (df_emissions["parameter"] == "co2_scope1")
            & (df_emissions["region"] == "Global")
        ),
        (idx + ["value"]),
    ]
    df_emissions_clinker_scope1 = (
        df_emissions_clinker_scope1.set_index(idx).groupby(idx).sum()
    )

    # get clinker scope 2 emissions
    df_emissions_clinker_scope2 = df_emissions.copy().loc[
        (
            (df_emissions["parameter"] == "co2_scope2")
            & (df_emissions["region"] == "Global")
        ),
        (idx + ["value"]),
    ]
    df_emissions_clinker_scope2 = (
        df_emissions_clinker_scope2.set_index(idx).groupby(idx).sum()
    )

    # get concrete & cement demand (assumption: demand == production)
    df_concrete_demand = df_outputs_demand_model.copy().loc[
        (df_outputs_demand_model["technology"] == "Concrete demand"), (idx + ["value"])
    ]
    df_concrete_demand = df_concrete_demand.set_index(idx).sort_index()
    df_cement_demand = df_outputs_demand_model.copy().loc[
        (df_outputs_demand_model["technology"] == "Cement demand"), (idx + ["value"])
    ]
    df_cement_demand = df_cement_demand.set_index(idx).sort_index()

    # get cement & concrete scope 2 emissions
    df_emissions_concrete_scope2 = df_outputs_demand_model.copy().loc[
        (df_outputs_demand_model["technology"] == "Concrete scope 2 emissions"),
        (idx + ["value"]),
    ]
    df_emissions_concrete_scope2 = df_emissions_concrete_scope2.set_index(
        idx
    ).sort_index()
    df_emissions_cement_scope2 = df_outputs_demand_model.copy().loc[
        (df_outputs_demand_model["technology"] == "Cement scope 2 emissions"),
        (idx + ["value"]),
    ]
    df_emissions_cement_scope2 = df_emissions_cement_scope2.set_index(idx).sort_index()

    # compute
    df_cement_scope1 = df_emissions_clinker_scope1.div(df_cement_demand)
    df_concrete_scope1 = df_emissions_clinker_scope1.div(df_concrete_demand)
    df_cement_scope2 = df_emissions_clinker_scope2.add(df_emissions_cement_scope2).div(
        df_cement_demand
    )
    df_concrete_scope2 = (
        df_emissions_clinker_scope2.add(df_emissions_cement_scope2)
        .add(df_emissions_concrete_scope2)
        .div(df_concrete_demand)
    )

    # aggregate
    df_cement_scope1.reset_index(inplace=True)
    df_concrete_scope1.reset_index(inplace=True)
    df_cement_scope2.reset_index(inplace=True)
    df_concrete_scope2.reset_index(inplace=True)
    df_cement_scope1["technology"] = "All"
    df_concrete_scope1["technology"] = "All"
    df_cement_scope2["technology"] = "All"
    df_concrete_scope2["technology"] = "All"
    df_cement_scope1["parameter"] = "Emissions intensity CO2 Scope1"
    df_concrete_scope1["parameter"] = "Emissions intensity CO2 Scope1"
    df_cement_scope2["parameter"] = "Emissions intensity CO2 Scope2"
    df_concrete_scope2["parameter"] = "Emissions intensity CO2 Scope2"
    df_cement_scope1["parameter_group"] = "Emissions intensity"
    df_concrete_scope1["parameter_group"] = "Emissions intensity"
    df_cement_scope2["parameter_group"] = "Emissions intensity"
    df_concrete_scope2["parameter_group"] = "Emissions intensity"
    df_cement_scope1["product"] = "Cement"
    df_concrete_scope1["product"] = "Concrete"
    df_cement_scope2["product"] = "Cement"
    df_concrete_scope2["product"] = "Concrete"
    df_cement_scope1["unit"] = "tCO2/t"
    df_concrete_scope1["unit"] = "tCO2/t"
    df_cement_scope2["unit"] = "tCO2/t"
    df_concrete_scope2["unit"] = "tCO2/t"

    df = pd.concat(
        [
            df_cement_scope1,
            df_concrete_scope1,
            df_cement_scope2,
            df_concrete_scope2,
        ]
    )

    return df


""" Number of plants """


def _get_number_plants_by_initial_net_zero(
    importer: IntermediateDataImporter,
    df_tech_roadmap: pd.DataFrame,
) -> pd.DataFrame:

    idx = ["product", "year", "region", "technology"]

    df_tech_roadmap = df_tech_roadmap.copy().loc[
        df_tech_roadmap["region"] != "Global", :
    ]

    # get tech characteristics to identify net-zero and initial plants
    df_tech_char = importer.get_technology_characteristics()[
        idx + ["technology_classification"]
    ]

    df = (
        pd.merge(
            left=df_tech_roadmap,
            right=df_tech_char,
            how="left",
            on=idx,
        )
        .set_index((idx + ["technology_classification"]))
        .div(ASSUMED_ANNUAL_PRODUCTION_CAPACITY)
    )

    # add global
    df_global = df.groupby([x for x in df.index.names if x != "region"]).sum()
    df_global["region"] = "Global"
    df_global_all_techs = (
        df.groupby([x for x in df.index.names if x not in ["region", "technology"]])
        .sum()
        .reset_index()
    )
    df_global_all_techs["region"] = "Global"
    df_global_all_techs["technology"] = df_global_all_techs["technology_classification"]
    # aggregate
    df_global = pd.concat(
        [
            df_global.reset_index().set_index(idx),
            df_global_all_techs.set_index(idx),
        ]
    )

    # aggregate
    df = pd.concat(
        [
            df.reset_index().set_index(idx).drop(columns="technology_classification"),
            df_global.reset_index()
            .set_index(idx)
            .drop(columns="technology_classification"),
        ]
    ).sort_index()

    return df.reset_index()


def _get_number_added_plants_by_initial_net_zero(
    df_number_plants: pd.DataFrame,
) -> pd.DataFrame:

    idx = ["product", "year", "region", "technology"]

    df = df_number_plants.copy()
    df = df.loc[
        (
            (df["region"] == "Global")
            & (df["technology"].isin(["initial", "end-state"]))
        ),
        :,
    ]
    df.set_index(keys=idx, inplace=True)

    # count added plants per year
    def _count_additions(row: pd.Series) -> pd.Series:
        row.sort_index(inplace=True)
        for i in np.arange(1, row.shape[0]):
            row.iloc[i, 0] -= row.iloc[i - 1, 1]
        return row

    df["total_plants"] = df["value"]
    df = df.groupby([x for x in idx if x != "year"]).apply(
        lambda x: _count_additions(x)
    )

    df.drop(columns="total_plants", inplace=True)

    return df.reset_index()


""" Cost """


def _calculate_weighted_average_lcoc(
    df_cost: pd.DataFrame,
    importer: IntermediateDataImporter,
) -> pd.DataFrame:
    """Calculate weighted average of LCOX across the supply mix in a given year."""

    agg_vars = ["product", "region"]

    # filter OPEX context
    if "opex_context" in df_cost.columns:
        df_cost = df_cost.loc[
            (df_cost["opex_context"] == f"value_{CCUS_CONTEXT[0]}"), :
        ]

    df = pd.DataFrame()
    # In every year, get LCOX of the asset based on the year it was commissioned and average according to desired
    #   aggregation
    for year in np.arange(START_YEAR, END_YEAR + 1):
        df_stack = importer.get_asset_stack(year)
        df_stack = df_stack.rename(columns={"year_commissioned": "year"})

        # Assume that assets built before start of model time horizon have LCOX of start year
        df_stack.loc[df_stack["year"] < START_YEAR, "year"] = START_YEAR

        # Add LCOX to each asset
        df_cost = df_cost.loc[df_cost["technology_origin"] == "New-build"]
        df_cost = df_cost.rename(columns={"technology_destination": "technology"})
        df_stack = df_stack.merge(
            df_cost, on=["product", "region", "technology", "year"], how="left"
        )

        # Calculate weighted average in all regions
        df_append = (
            (
                df_stack.copy()
                .groupby(agg_vars)
                .apply(
                    lambda x: np.average(
                        x["lcox"], weights=x["annual_production_volume"]
                    )
                )
            )
            .reset_index(drop=False)
            .rename(columns={0: "value"})
        )
        # calculate weighted average globally
        df_append_global = (
            (
                df_stack.copy()
                .groupby("product")
                .apply(
                    lambda x: np.average(
                        x["lcox"], weights=x["annual_production_volume"]
                    )
                )
            )
            .reset_index(drop=False)
            .rename(columns={0: "value"})
        )
        df_append_global["region"] = "Global"
        df_append = pd.concat([df_append, df_append_global])
        df_append["year"] = year

        # concatenate
        df = pd.concat([df, df_append])

    df["technology"] = "All"

    return df


def _calculate_weighted_average_lcoc_relative_change(
    df_weighted_average_lcoc: pd.DataFrame,
) -> pd.DataFrame:

    df = (
        df_weighted_average_lcoc.copy()
        .set_index([x for x in df_weighted_average_lcoc.columns if x != "value"])
        .sort_index()
    )

    def _get_rel_change(row: pd.Series):
        lcoc_start = row.iloc[0, 0]
        row -= lcoc_start
        row /= lcoc_start
        row += float(1)
        row *= float(100)
        return row

    df = df.groupby([x for x in df.index.names if x != "year"]).apply(
        lambda x: _get_rel_change(x)
    )

    return df.reset_index()


def _export_and_plot_weighted_average_lcox_by_region(
    pathway_name: str,
    sensitivity: str,
    importer: IntermediateDataImporter,
    df_weighted_average_lcox: pd.DataFrame,
    unit: str,
    technology_layout: dict,
):
    importer.export_data(
        df=df_weighted_average_lcox,
        filename=f"{pathway_name}_weighted_avg_lcoc.csv",
        export_dir="final/cost/lcoc",
        index=True,
    )

    regions = df_weighted_average_lcox.reset_index()["region"].unique()

    for region in regions:
        df_weighted_average_lcox_region = df_weighted_average_lcox.loc[
            (df_weighted_average_lcox["region"] == region), :
        ]

        fig_line = px.line(
            data_frame=df_weighted_average_lcox_region,
            x="year",
            y="value",
            color="technology",
            labels={
                "year": "Year",
                "value": f"Weighted average LCOC in {unit}",
            },
            title=f"{region}: Weighted average LCOC ({pathway_name}_{sensitivity})",
            category_orders={"technology": list(technology_layout)},
            color_discrete_map=technology_layout,
        )

        plot(
            figure_or_data=fig_line,
            filename=f"{importer.final_path}/cost/lcoc/{pathway_name}_weighted_avg_lcoc_{region}.html",
            auto_open=False,
        )


def _export_greenfield_lcoc(
    importer: IntermediateDataImporter,
    pathway_name: str,
):
    df_lcoc = importer.get_lcox()

    # filter
    df_lcoc = df_lcoc.loc[
        (df_lcoc["switch_type"] == "greenfield"),
        ["year", "region", "technology_destination", f"value_{CCUS_CONTEXT[0]}"],
    ]

    # long to wide
    df_lcoc = df_lcoc.pivot(
        index=["region", "technology_destination"],
        columns="year",
        values=f"value_{CCUS_CONTEXT[0]}",
    )

    importer.export_data(
        df=df_lcoc,
        filename=f"{pathway_name}_lcoc_greenfield.csv",
        export_dir="final/cost",
        index=True,
    )


""" Resource consumption """


def _calculate_resource_consumption_gj(
    importer: IntermediateDataImporter, clinker_production_only: bool = False
) -> pd.DataFrame:
    """Calculate the consumption of all energy resources by year and region (incl. Global).

    Args:
        importer ():
        clinker_production_only (): If True, function will only output energy consumption for heat energy
            (ignoring carbon capture heat as well as cement & concrete energy demand)

    Returns:

    """

    if clinker_production_only:
        logger.info(f"-- Calculating resource consumption for clinker production")
    else:
        logger.info(f"-- Calculating resource consumption")

    idx = ["product", "region", "technology"]

    df_inputs_energy = importer.get_imported_input_data(
        input_metrics={"Technology cards": ["inputs_energy"]}
    )["inputs_energy"]

    df_resource_consumption = pd.DataFrame()
    for year in MODEL_YEARS:

        # prepare current technology stack
        df_stack = importer.get_asset_stack(year)
        df_stack.rename(columns={"annual_production_volume": "value"}, inplace=True)
        df_stack = df_stack[["product", "region", "technology", "value"]]
        df_stack = df_stack.set_index(idx).groupby(idx).sum()
        # unit df_stack: [Mt Clk]
        df_stack *= 1e6
        # unit df_stack: [t Clk]

        # prepare energy inputs
        df_inputs_energy_year = df_inputs_energy.copy().loc[
            (df_inputs_energy["year"] == year), :
        ]
        df_inputs_energy_year.rename(
            columns={"technology_destination": "technology"}, inplace=True
        )
        df_inputs_energy_year = df_inputs_energy_year[idx + ["metric", "value"]]
        dict_inputs_energy_year = dict.fromkeys(RESOURCE_CONSUMPTION_METRICS)
        for resource in dict_inputs_energy_year.keys():
            if clinker_production_only:
                df_resource = df_inputs_energy_year.loc[
                    (
                        (
                            df_inputs_energy_year["metric"].isin(
                                RESOURCE_CONSUMPTION_METRICS[resource]
                            )
                        )
                        & (~(df_inputs_energy_year["metric"].str.contains("CC")))
                    ),
                    :,
                ]
            else:
                df_resource = df_inputs_energy_year.loc[
                    df_inputs_energy_year["metric"].isin(
                        RESOURCE_CONSUMPTION_METRICS[resource]
                    ),
                    :,
                ]
            df_resource.set_index(keys=(idx + ["metric"]), inplace=True)
            df_resource = df_resource.groupby(idx).sum()
            dict_inputs_energy_year[resource] = df_resource
        # unit dict_inputs_energy_year: [GJ / t Clk]

        # resource consumption = production volume * resource intensity
        dict_resource_consumption_year = dict.fromkeys(RESOURCE_CONSUMPTION_METRICS)
        for resource in dict_resource_consumption_year.keys():
            df_consumption = df_stack.mul(dict_inputs_energy_year[resource]).dropna(
                how="all"
            )
            # aggregate
            df_consumption = df_consumption.groupby(
                [x for x in idx if x != "technology"]
            ).sum()

            # add global
            df_consumption_global = df_consumption.copy().groupby(["product"]).sum()
            df_consumption_global["region"] = "Global"
            df_consumption = df_consumption.reset_index()
            df_consumption_global = df_consumption_global.reset_index()
            df_consumption = pd.concat(
                [
                    df_consumption,
                    df_consumption_global[[x for x in df_consumption.columns]],
                ]
            ).reset_index(drop=True)

            df_consumption["parameter"] = resource
            df_consumption["year"] = year
            dict_resource_consumption_year[resource] = df_consumption

        # append
        df_resource_consumption = pd.concat(
            [df_resource_consumption]
            + [
                dict_resource_consumption_year[x]
                for x in dict_resource_consumption_year.keys()
            ]
        )

    df_resource_consumption["unit"] = "GJ"
    if clinker_production_only:
        df_resource_consumption["parameter_group"] = "Energy from clinker production"
    else:
        df_resource_consumption["parameter_group"] = "Energy"
        # add electricity demand from concrete mixing and cement grinding (from demand model)
        df_cntcmt_elec = importer.get_outputs_demand_model()
        df_cntcmt_elec = df_cntcmt_elec.loc[
            df_cntcmt_elec["technology"].isin(
                ["Concrete electricity consumption", "Cement electricity consumption"]
            )
        ]
        df_cntcmt_elec["product"] = np.nan
        df_cntcmt_elec.loc[
            (df_cntcmt_elec["technology"] == "Concrete electricity consumption"),
            "product",
        ] = "Concrete"
        df_cntcmt_elec.loc[
            (df_cntcmt_elec["technology"] == "Cement electricity consumption"),
            "product",
        ] = "Cement"
        df_cntcmt_elec.drop(columns="technology", inplace=True)
        df_cntcmt_elec["parameter"] = "Electricity"
        df_cntcmt_elec["parameter_group"] = "Energy"
        df_cntcmt_elec["unit"] = "GJ"
        df_cntcmt_elec = df_cntcmt_elec[list(df_resource_consumption.columns)]
        df_resource_consumption = pd.concat([df_resource_consumption, df_cntcmt_elec])

    df_resource_consumption["technology"] = "All"

    return df_resource_consumption.reset_index(drop=True)


def _convert_resource_consumption(
    df_resource_consumption: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert the resource consumption dataframe from GJ to the units defined in "units"

    Args:
        df_resource_consumption (): [GJ]

    Returns:
        df_resource_consumption (): [{cf. units dictionary}]
    """

    units = {
        "Coal": "Mt",
        "Natural gas": "bcm",
        "Electricity": "TWh",
        "Biomass (including biomass from mixed fuels)": "PJ",
        "Waste of fossil origin (including fossil fuel from mixed fuels)": "PJ",
        "Alternative fuels": "PJ",
        "Hydrogen": "Mt H2",
    }

    conversion_factors_from_gj = {
        "Coal": COAL_GJ_T / 1e6,
        "Natural gas": NATURAL_GAS_GJ_BCM,
        "Electricity": ELECTRICITY_GJ_TWH,
        "Biomass (including biomass from mixed fuels)": 1 / 1e6,
        "Waste of fossil origin (including fossil fuel from mixed fuels)": 1 / 1e6,
        "Alternative fuels": 1 / 1e6,
        "Hydrogen": HYDROGEN_GJ_T / 1e6,
    }

    # Convert values to desired units
    df = df_resource_consumption.copy()
    for resource in units.keys():
        df.loc[df["parameter"] == resource, "value"] *= conversion_factors_from_gj[
            resource
        ]
        df.loc[df["parameter"] == resource, "unit"] = units[resource]

    return df


def _export_and_plot_resource_consumption(
    pathway_name: str,
    sensitivity: str,
    importer: IntermediateDataImporter,
    df_resource_consumption: pd.DataFrame,
    unit: str,
):

    # export
    importer.export_data(
        df=df_resource_consumption,
        filename=f"{pathway_name}_{sensitivity}_resource_consumption.csv",
        export_dir="final/resource_consumption",
        index=False,
    )

    # plot
    df_plot = df_resource_consumption.loc[
        (df_resource_consumption["region"] == "Global"), :
    ]
    fig_line = px.line(
        data_frame=df_plot,
        x="year",
        y="value",
        color="parameter",
        labels={
            "year": "Year",
            "value": f"Resource consumption in {unit}",
        },
        title=f"Resource consumption ({pathway_name}_{sensitivity})",
    )

    plot(
        figure_or_data=fig_line,
        filename=f"{importer.final_path}/resource_consumption/{pathway_name}_{sensitivity}_resource_consumption.html",
        auto_open=False,
    )


""" helper functions """


def _format_output_data(
    df: pd.DataFrame,
    pathway_name: str,
    sensitivity: str,
    parameter_group: str | None = None,
    parameter: str | None = None,
    unit: str | None = None,
) -> pd.DataFrame:
    """
    Format output data

    Args:
        df (): df to be formatted (must have exactly one "value" column)
        pathway_name ():
        sensitivity ():
        parameter_group ():
        parameter ():
        unit ():

    Returns:

    """

    df_formatted = df.copy()
    idx_formatted = (
        ["scenario", "sector"]
        + [
            x
            for x in df_formatted.columns
            if x not in ["value", "year", "parameter_group", "parameter", "unit"]
        ]
        + ["parameter_group", "parameter", "unit"]
    )

    # add columns
    df_formatted["scenario"] = f"{pathway_name}_{sensitivity}"
    df_formatted["sector"] = SECTOR
    if parameter_group is not None:
        df_formatted["parameter_group"] = parameter_group
    if parameter is not None:
        df_formatted["parameter"] = parameter
    if unit is not None:
        df_formatted["unit"] = unit

    # pivot
    df_formatted = (
        df_formatted.pivot(
            index=idx_formatted,
            columns="year",
            values="value",
        )
        .fillna(value=float(0))
        .sort_index()
        .reset_index()
    )

    # order columns
    df_formatted = df_formatted[
        idx_formatted + [x for x in list(MODEL_YEARS) if x in df_formatted.columns]
    ]

    return df_formatted


def _get_emission_factor_pre_capture(
    row: pd.Series,
    importer: IntermediateDataImporter,
    df_emissions: pd.DataFrame,
    value_if_none: float,
) -> pd.Series:
    """
    Adjusts a row in df_emissions such that df_emissions["co2_scope1"] is the respective emission factor pre capturing

    Args:
        row ():
        importer ():
        df_emissions ():
        value_if_none (): Emission factor that will be set if MAP_EMISSION_FACTOR_PRE_CAPTURE maps to None

    Returns:

    """

    if MAP_EMISSION_FACTOR_PRE_CAPTURE[row.loc["technology"]] is None:
        # set to value_if_none
        co2_scope1 = value_if_none
    elif MAP_EMISSION_FACTOR_PRE_CAPTURE[row.loc["technology"]] == "process_only":
        # set to process emissions
        df_process_emissions = importer.get_imported_input_data(
            input_metrics={"Shared inputs - Emissivity": ["emissivity_co2"]}
        )["emissivity_co2"]
        co2_scope1 = df_process_emissions.loc[
            (
                (df_process_emissions["region"] == row.loc["region"])
                & (df_process_emissions["year"] == row.loc["year"])
                & (df_process_emissions["metric"] == "Calcination process emissions")
            ),
            "value",
        ].squeeze()
    else:
        # set to corresponding technology's emission factor
        co2_scope1 = df_emissions.loc[
            (
                (df_emissions["year"] == row.loc["year"])
                & (df_emissions["region"] == row.loc["region"])
                & (
                    df_emissions["technology"]
                    == MAP_EMISSION_FACTOR_PRE_CAPTURE[row.loc["technology"]]
                )
            ),
            "co2_scope1",
        ].squeeze()

    return co2_scope1
