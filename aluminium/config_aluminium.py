import numpy as np

SECTOR = "aluminium"
LOG_LEVEL = "DEBUG"
MODEL_SCOPE = "Global"

PATHWAYS = [
    "bau",
    "fa",
    "lc",
    "cc",
]

PATHWAYS_WITH_TECHNOLOGY_MORATORIUM = ["lc", "cc"]
SCOPES_CO2_COST = [
    "scope1",
    "scope2",
]

### RUN CONFIGURATION ###

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
RUN_PARALLEL = False
APPLY_CARBON_COST = False

### MODEL DECISION PARAMETERS ###
START_YEAR = 2020
END_YEAR = 2050
MODEL_YEARS = np.arange(START_YEAR, END_YEAR + 1)


REGIONAL_PRODUCTION_SHARES = {
    "China - North": 0.3,
    "China - North West": 0.3,
    "China - North East": 0.3,
    "China - Central": 0.3,
    "China - South": 0.3,
    "China - East": 0.3,
    "Rest of Asia": 0.75,
    "North America": 0.75,
    "Russia": 0.75,
    "Rest of Europe": 0.75,
    "Middle East": 0.75,
    "Africa": 0.75,
    "South America": 0.75,
    "Oceania": 0.75,
    "Canada": 0.75,
    "Scandinavia": 0.75,
    "US": 0.75,
}

# Sensitivities: low fossil prices, constrained CCS, BAU demand, low demand
ALL_SENSITIVITIES = [
    "def",
    "Carbon Price_0.2",
    "Carbon Price_-0.2",
    "Coal Price_0.2",
    "Coal Price_-0.2",
    "Grid and PPA Prices_0.2",
    "Grid and PPA Prices_-0.2",
    "Hydrogen Price_0.2",
    "Hydrogen Price_-0.2",
    "Natural Gas Price_0.2",
    "Natural Gas Price_-0.2",
]
SENSITIVITIES = {
    "bau": ["def"],  # ALL_SENSITIVITIES,
    "fa": ["def"],
    "lc": ["def"],  # ALL_SENSITIVITIES,
}
INVESTMENT_CYCLE = 10  # years
CUF_LOWER_THRESHOLD = 0.6
CUF_UPPER_THRESHOLD = 0.95
COST_METRIC_CUF_ADJUSTMENT = "lcox"
# Products produced by each sector
PRODUCTS = ["Aluminium"]

OUTPUT_WRITE_PATH = "aluminium/data/outputs"

# Share of assets renovated annually (limits number of brownfield transitions)
ANNUAL_RENOVATION_SHARE = 0.2
# Specify whether sector uses region-specific or asset-specific data for initial asset stack
INITIAL_ASSET_DATA_LEVEL = "individual_assets"
# Scope of the model run - to be specified
MODEL_SCOPE = "Global"

# Override asset parameters; annual production capacity in Mt/year
ASSUMED_ANNUAL_PRODUCTION_CAPACITY = 1

# Year from which newbuild capacity must have transition or end-state technology
TECHNOLOGY_MORATORIUM = 2030
# Control for how many years is allowed to use transition technologies once the moratorium is enable
TRANSITIONAL_PERIOD_YEARS = 10
# Emission scopes included in data analysis
EMISSION_SCOPES = [
    "scope1",
    "scope2",
]
# Emissions
GHGS = ["co2"]

### RANKING OF TECHNOLOGY SWITCHES ###
RANKING_COST_METRIC = "tco"
BIN_METHODOLOGY = "histogram"
NUMBER_OF_BINS_RANKING = 50
GHGS_RANKING = ["co2"]
EMISSION_SCOPES_RANKING = ["scope1", "scope2"]

TRANSITION_TYPES = [
    "decommission",
    "greenfield",
    "brownfield_renovation",
    "brownfield_newbuild",
]

RANK_TYPES = ["decommission", "greenfield", "brownfield"]

# set the switch types that will update an assets commissioning year
SWITCH_TYPES_UPDATE_YEAR_COMMISSIONED = ["brownfield_rebuild"]


CARBON_BUDGET_SECTOR_CSV = True

residual_share = 0.05
emissions_2020 = 0.62  # Gt CO2 (scope 1 and 2)
SECTORAL_CARBON_PATHWAY = {
    "emissions_start": emissions_2020,
    "emissions_end": residual_share * emissions_2020,
    "action_start": 2023,
}

# Ranking configuration depends on type of technology switch and pathway
lc_weight_cost = 1.0
lc_weight_emissions = 0.0
fa_weight_cost = 0.0
fa_weight_emissions = 1.0
RANKING_CONFIG = {
    "greenfield": {
        "bau": {
            "cost": 1.0,
            "emissions": 0.0,
        },
        "fa": {
            "cost": 0.0,
            "emissions": 1.0,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
        "cc": {
            "cost": 1.0,
            "emissions": 0.0,
        },
    },
    "brownfield": {
        "bau": {
            "cost": 1.0,
            "emissions": 0.0,
        },
        "fa": {
            "cost": 0.0,
            "emissions": 1.0,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
        "cc": {
            "cost": 1.0,
            "emissions": 0.0,
        },
    },
    "decommission": {
        "bau": {
            "cost": 1,
            "emissions": 0,
        },
        "fa": {
            "cost": 0.0,
            "emissions": 1.0,
        },
        "lc": {
            "cost": lc_weight_cost,
            "emissions": lc_weight_emissions,
        },
        "cc": {
            "cost": 1.0,
            "emissions": 0.0,
        },
    },
}

### CONSTRAINTS ###

CONSTRAINTS_TO_APPLY = {
    "bau": [],
    "cc": ["rampup_constraint"],
    "lc": ["emissions_constraint", "rampup_constraint"],
    "fa": ["emissions_constraint", "rampup_constraint"],
}

YEAR_2050_EMISSIONS_CONSTRAINT = 2051

# Technology ramp-up parameters
TECHNOLOGY_RAMP_UP_CONSTRAINT = {
    "init_maximum_asset_additions": 6,  # 10
    "maximum_asset_growth_rate": 0.5,  # 0.25
    "years_rampup_phase": 8,  # 5
}
