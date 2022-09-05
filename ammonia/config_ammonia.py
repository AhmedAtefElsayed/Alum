"""Configuration of the MPP Ammonia model."""
import logging

import numpy as np

SECTOR = "ammonia"
# Scope of the model run - to be specified
MODEL_SCOPE = "Global"

INITIAL_ASSET_DATA_LEVEL = "regional"

### RUN CONFIRGUATION ###
LOG_LEVEL = "DEBUG"
LOG_FORMATTER = logging.Formatter(
    "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
)
RUN_PARALLEL = False
run_config = {
    "IMPORT_DATA",
    "CALCULATE_VARIABLES",
    "APPLY_IMPLICIT_FORCING",
    "MAKE_RANKINGS",
    "SIMULATE_PATHWAY",
    "CALCULATE_OUTPUTS",
    "CREATE_DEBUGGING_OUTPUTS",
    # "EXPORT_OUTPUTS",
    # "PLOT_AVAILABILITIES"
    # "MERGE_OUTPUTS"
}
# Integrate current project pipeline or not
BUILD_CURRENT_PROJECT_PIPELINE = True

# Delays for brownfield transitions to make the model more realistic
BROWNFIELD_RENOVATION_START_YEAR = 2025  # means retrofit plants come online in 2026

BROWNFIELD_REBUILD_START_YEAR = 2027  # means rebuild plants come online in 2028

START_YEAR = 2020
END_YEAR = 2050
MODEL_YEARS = np.arange(START_YEAR, END_YEAR + 1)
PRODUCTS = ["Ammonia", "Ammonium nitrate", "Urea"]
# Override asset parameters; annual production capacity in Mt/year
ASSUMED_ANNUAL_PRODUCTION_CAPACITY = 1

# Override asset parameters; annual production capacity in Mt/year
# Ratios for calculating electrolysis capacity
H2_PER_AMMONIA = 0.176471
AMMONIA_PER_UREA = 0.565724
AMMONIA_PER_AMMONIUM_NITRATE = 0.425534
ammonia_typical_plant_capacity_Mt = (2000 * 365) / 1e6

ASSUMED_ANNUAL_PRODUCTION_CAPACITY_MT = {
    "Ammonia": ammonia_typical_plant_capacity_Mt,
    "Urea": ammonia_typical_plant_capacity_Mt / AMMONIA_PER_UREA,
    "Ammonium nitrate": ammonia_typical_plant_capacity_Mt
    / AMMONIA_PER_AMMONIUM_NITRATE,
    "Aluminium": 1,
}

### PATHWAYS, SENSITIVITIES AND CARBON COSTS ###
PATHWAYS = [
    "lc",
    # "fa",
    # "bau",
]

SENSITIVITIES = [
    "def",
    # "ng_partial",
    # "ng_high",
    # "ng_low",
]

CARBON_COSTS = [
    0,
    50,
    100,
    150,
    200,
    250,
]

REGIONAL_PRODUCTION_SHARES = {
    "Africa": 0.4,
    "China": 0.4,
    "Europe": 0.4,
    "India": 0.4,
    "Latin America": 0.4,
    "Middle East": 0.4,
    "North America": 0.4,
    "Oceania": 0.4,
    "Russia": 0.4,
    "Rest of Asia": 0.4,
}

MAP_LOW_COST_POWER_REGIONS = {
    "Middle East": "Saudi Arabia",
    "Africa": "Namibia",
    "Oceania": "Australia",
    "Latin America": "Brazil",
}

### STANDARD ASSUMPTIONS FOR AMMOINA PLANTS ###
STANDARD_CUF = 0.95
STANDARD_LIFETIME = 30  # years
STANDARD_WACC = 0.08

### EMISSIONS CALCULATIONS ###
GHGS = ["co2", "n2o", "ch4"]

### COST CALCULATIONS ###
GROUPING_COLS_FOR_NPV = [
    "product",
    "technology_origin",
    "region",
    "switch_type",
    "technology_destination",
]

SCOPES_CO2_COST = ["scope1", "scope2", "scope3_upstream"]

### CONSTRAINTS ON POSSIBLE TECHNOLOGY SWITCHES ###

# Regions where geological H2 storage is not allowed because no salt caverns are available
REGIONS_SALT_CAVERN_AVAILABILITY = {
    "Africa": "yes",
    "China": "yes",
    "Europe": "yes",
    "India": "no",
    "Latin America": "yes",
    "Middle East": "yes",
    "North America": "yes",
    "Oceania": "yes",
    "Russia": "yes",
    "Rest of Asia": "yes",
}

# List of regions
REGIONS = [
    "Africa",
    "China",
    "Europe",
    "India",
    "Latin America",
    "Middle East",
    "North America",
    "Oceania",
    "Russia",
    "Rest of Asia",
    "Brazil",
    "Australia",
    "Namibia",
    "Saudi Arabia",
]


# Maximum share of global demand that can be supplied by one region
MAXIMUM_GLOBAL_DEMAND_SHARE_ONE_REGION = 0.3

TECHNOLOGIES_MAXIMUM_GLOBAL_DEMAND_SHARE = [
    "Biomass Gasification + ammonia synthesis",
    "Biomass Digestion + ammonia synthesis",
    "Methane Pyrolysis + ammonia synthesis",
]

# TODO: transfer this to input file
MAXIMUM_GLOBAL_DEMAND_SHARE = {
    2020: 0.02,
    2021: 0.02,
    2022: 0.02,
    2023: 0.02,
    2024: 0.02,
    2025: 0.02,
    2026: 0.02,
    2027: 0.02,
    2028: 0.02,
    2029: 0.02,
    2030: 0.02,
    2031: 0.02,
    2032: 0.02,
    2033: 0.02,
    2034: 0.02,
    2035: 0.02,
    2036: 0.02,
    2037: 0.02,
    2038: 0.02,
    2039: 0.02,
    2040: 0.02,
    2041: 1,
    2042: 1,
    2043: 1,
    2044: 1,
    2045: 1,
    2046: 1,
    2047: 1,
    2048: 1,
    2049: 1,
    2050: 1,
}

# Year from which newbuild capacity must have transition or end-state technology
TECHNOLOGY_MORATORIUM = 2020

# Duration for which transition technologies are still allowed after the technology moratorium comes into force
TRANSITIONAL_PERIOD_YEARS = 30

### RANKING OF TECHNOLOGY SWITCHES ###
RANKING_COST_METRIC = "lcox"
COST_METRIC_RELATIVE_UNCERTAINTY = 0.05
GHGS_RANKING = ["co2"]
EMISSION_SCOPES_RANKING = ["scope1", "scope2", "scope3_upstream"]
# Emission scopes included in data analysis
EMISSION_SCOPES = ["scope1", "scope2", "scope3_upstream", "scope3_downstream"]
# list to define the columns that the ranking will groupby and create a separate ranking for
UNCERTAINTY_RANKING_GROUPS = ["year"]

TRANSITION_TYPES = [
    "decommission",
    "greenfield",
    "brownfield_renovation",
    "brownfield_newbuild",
]

RANK_TYPES = ["decommission", "greenfield", "brownfield"]

# Ranking configuration depends on type of technology switch and pathway
lc_weight_cost = 0.8
lc_weight_emissions = 1 - lc_weight_cost
fa_weight_cost = 0.01
fa_weight_emissions = 1 - fa_weight_cost
RANKING_CONFIG = {
    "greenfield": {
        "bau": {
            "cost": 1.0,
            "emissions": 0.0,
        },
        "fa": {
            "cost": fa_weight_cost,
            "emissions": fa_weight_emissions,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
    },
    "brownfield": {
        "bau": {
            "cost": 1.0,
            "emissions": 0.0,
        },
        "fa": {
            "cost": fa_weight_cost,
            "emissions": fa_weight_emissions,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
    },
    "decommission": {
        "bau": {
            "cost": 1,
            "emissions": 0,
        },
        "fa": {
            "cost": fa_weight_cost,
            "emissions": fa_weight_emissions,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
    },
}

### CONSTRAINTS ###
SET_CO2_STORAGE_CONSTRAINT = True
CO2_STORAGE_CONSTRAINT_TYPE = "annual_addition"    # "annual_cumulative", "annual_addition", "total_cumulative", or None
CUF_LOWER_THRESHOLD = 0.5
CUF_UPPER_THRESHOLD = 0.95
INVESTMENT_CYCLE = 20  # years

CONSTRAINTS_TO_APPLY = {
    "bau": [None],
    "lc": [
        "emissions_constraint",
        "rampup_constraint",
        "co2_storage_constraint",
        "electrolysis_capacity_addition_constraint",
        "demand_share_constraint",
    ],
    "fa": ["co2_storage_constraint"],
}

YEAR_2050_EMISSIONS_CONSTRAINT = 2050

# Share of assets renovated annually (limits number of brownfield transitions)
ANNUAL_RENOVATION_SHARE = 0.5
# Technology ramp-up parameters
TECHNOLOGY_RAMP_UP_CONSTRAINT = {
    "init_maximum_asset_additions": 10,
    "maximum_asset_growth_rate": 0.7,
    "years_rampup_phase": 5,
}

CARBON_BUDGET_SECTOR_CSV = False
residual_share = 0.05
emissions_2020 = 0.62  # Gt CO2 (scope 1 and 2)

SECTORAL_CARBON_PATHWAY = {
    "emissions_start": emissions_2020,
    "emissions_end": residual_share * emissions_2020,
    "action_start": 2023,
}

# Increase in cost metric required to enact a brownfield renovation or brownfield rebuild transition
COST_METRIC_DECREASE_BROWNFIELD = 0.05

# Regional ban of technologies (sector-specific)
REGIONAL_TECHNOLOGY_BAN = {
    "China": [
        "Natural Gas SMR + ammonia synthesis",
        "Natural Gas ATR + CCS + ammonia synthesis",
        "Oversized ATR + CCS",
        "Natural Gas SMR + CCS (process emissions only) + ammonia synthesis",
        "Natural Gas SMR + CCS + ammonia synthesis",
        "Electrolyser + SMR + ammonia synthesis",
        "GHR + CCS + ammonia synthesis",
        "ESMR Gas + CCS + ammonia synthesis",
    ]
}
