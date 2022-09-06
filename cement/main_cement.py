"""Execute the MPP Cement model."""

import itertools

# Library imports
import multiprocessing as mp

from cement.config.config_cement import (
    PATHWAYS_SENSITIVITIES,
    PRODUCTS,
    RUN_PARALLEL,
    SECTOR,
    run_config,
)
from cement.solver.implicit_forcing import apply_implicit_forcing
from cement.solver.output_processing import calculate_outputs
from cement.solver.preprocess import import_and_preprocess
from cement.solver.ranking import make_rankings
from cement.solver.ranking_inputs import get_ranking_inputs
from cement.solver.simulate import simulate_pathway

# Shared imports
from mppshared.config import LOG_LEVEL

# Initialize logger
from mppshared.utility.utils import get_logger

logger = get_logger(__name__)
logger.setLevel(LOG_LEVEL)

funcs = {
    "IMPORT_DATA": import_and_preprocess,
    "CALCULATE_VARIABLES": get_ranking_inputs,
    "APPLY_IMPLICIT_FORCING": apply_implicit_forcing,
    "MAKE_RANKINGS": make_rankings,
    "SIMULATE_PATHWAY": simulate_pathway,
    "CALCULATE_OUTPUTS": calculate_outputs,
    # "CREATE_DEBUGGING_OUTPUTS": create_debugging_outputs,
}


def _run_model(pathway_name: str, sensitivity: str):
    for name, func in funcs.items():
        if name in run_config:
            logger.info(
                f"Running pathway {pathway_name} sensitivity {sensitivity} section {name}"
            )
            func(
                pathway_name=pathway_name,
                sensitivity=sensitivity,
                sector=SECTOR,
                products=PRODUCTS,
            )


def run_model_sequential(runs: list):
    """Run model sequentially, slower but better for debugging"""
    # TODO: Pass carbon cost trajectories into the model
    for pathway_name, sensitivity in runs:
        _run_model(pathway_name=pathway_name, sensitivity=sensitivity)


def run_model_parallel(runs: list):
    """Run model in parallel, faster but harder to debug"""
    n_cores = mp.cpu_count()
    logger.info(f"{n_cores} cores detected")
    pool = mp.Pool(processes=n_cores - 1)
    logger.info(f"Running model for scenario/sensitivity {runs}")
    for pathway, sensitivity in runs:
        pool.apply_async(_run_model, args=(pathway, sensitivity))
    pool.close()
    pool.join()


def main():
    logger.info(f"Running model for {SECTOR}")

    runs = []
    for pathway, sensitivities in PATHWAYS_SENSITIVITIES.items():
        for sensitivity in sensitivities:
            runs.append((pathway, sensitivity))
    if RUN_PARALLEL:
        run_model_parallel(runs)
    else:
        run_model_sequential(runs)


if __name__ == "__main__":
    main()