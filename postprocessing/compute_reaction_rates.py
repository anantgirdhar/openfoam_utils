import pickle
import sys
import textwrap
from pathlib import Path

import cantera as ct
import numpy as np
from tqdm import tqdm

from rwopenfoam import openfoam_to_pickle, pickle_to_openfoam


def process_openfoam_solution(force=False):
    time_dirs = []

    case_dir = Path(".")
    for time_dir in case_dir.iterdir():
        # Skip any non-time directories
        if not time_dir.is_dir():
            continue
        try:
            float(time_dir.name)
        except ValueError:
            continue
        # Process each time directory
        time_dirs.append(time_dir.name)
        pickle_filepath = case_dir / f"solution_{time_dir.name}.p"
        if pickle_filepath.is_file() and not force:
            continue
        else:
            openfoam_to_pickle(time_dir, pickle_filepath, force=True)

    time_dirs.sort(key=float)
    return time_dirs


def load_timestep(timestamp):
    with open(f"solution_{timestamp}.p", "rb") as pfile:
        data = pickle.load(pfile)
    return data


def write_timestep_pickle(pickle_filepath, timestamp, solution, force=False):
    if not force and pickle_filepath.is_file():
        raise FileExistsError(f"{pickle_filepath} already exists.")
    with open(pickle_filepath, "wb") as pfile:
        pickle.dump(solution, pfile)


def get_value(ofdata, var, index):
    try:
        iter(ofdata[var]["data"])
    except TypeError:
        # This is not iterable
        # It is probably a uniform value
        return ofdata[var]["data"]
    else:
        return ofdata[var]["data"][index]


def verify_OF_cantera_consistency(ofdata):
    # Load this data into cantera one grid point at a time and extract the
    # things we want
    gas = ct.Solution("gri30.yaml")
    # Verify that we have all the species that cantera is expecting
    of_vars = set(ofdata.keys())
    cantera_species = [sp.name for sp in gas.species()]
    if (
        not set(cantera_species).issubset(of_vars)
        and "Ydefault" not in of_vars
    ):
        raise ValueError(
            textwrap.dedent(
                f"""\
                The OpenFOAM solution does not all the species required by cantera
                OpenFOAM variables: {of_vars}
                Cantera species: {set(cantera_species)}
                """
            )
        )
    extra_of_vars = of_vars - set(cantera_species)
    extra_required_of_vars = {"T", "p"}
    extra_allowed_of_vars = {"U", "Qdot", "phi", "Ydefault", "alphat"}
    if not extra_required_of_vars.issubset(extra_of_vars):
        raise ValueError(
            textwrap.dedent(
                f"""\
        The OpenFOAM solution does not have the required variables
        OpenFOAM variables: {extra_of_vars}
        Required variables: {extra_required_of_vars}
        """
            )
        )

    extra_of_vars -= extra_required_of_vars
    if not extra_of_vars.issubset(extra_allowed_of_vars):
        raise ValueError(
            textwrap.dedent(
                f"""\
                The OpenFOAM solution has variables that are not allowed
                OpenFOAM variables: {extra_of_vars}
                Allowed variables: {extra_allowed_of_vars}
                """
            )
        )


def compute_rates(ofdata):
    verify_OF_cantera_consistency(ofdata)
    cantera_species = [sp.name for sp in ct.Solution("gri30.yaml").species()]
    computed_data = {}
    # First create space for all the newly computed fields
    for sp in cantera_species:
        computed_data[f"cr_{sp}_computed"] = {
            "type": "volScalarField",
            "dimensions": [0, 0, -1, 0, 0, 0, 0],
            "data": [],
        }
        computed_data[f"dr_{sp}_computed"] = {
            "type": "volScalarField",
            "dimensions": [0, 0, -1, 0, 0, 0, 0],
            "data": [],
        }
        computed_data["HRR_computed"] = {
            "type": "volScalarField",
            "dimensions": [1, -1, -3, 0, 0, 0, 0],
            "data": [],
        }
    num_grid_points = len(ofdata["T"]["data"])
    for i in tqdm(range(num_grid_points)):
        T = get_value(ofdata, "T", i)
        p = get_value(ofdata, "p", i)
        Y = np.array([get_value(ofdata, sp, i) for sp in cantera_species])
        # Create a new solution object to be safe?
        # This might not be required but I wonder how much it hurts
        gas = ct.Solution("gri30.yaml")
        gas.TPY = T, p, Y
        for i, sp in enumerate(cantera_species):
            computed_data[f"cr_{sp}_computed"]["data"].append(
                gas.creation_rates[i]
            )
            computed_data[f"dr_{sp}_computed"]["data"].append(
                gas.destruction_rates[i]
            )
        computed_data["HRR_computed"]["data"].append(gas.heat_release_rate)
    for i, sp in enumerate(cantera_species):
        computed_data[f"cr_{sp}_computed"]["data"] = np.array(
            computed_data[f"cr_{sp}_computed"]["data"]
        )
        computed_data[f"dr_{sp}_computed"]["data"] = np.array(
            computed_data[f"dr_{sp}_computed"]["data"]
        )
        computed_data["HRR_computed"]["data"] = np.array(
            computed_data["HRR_computed"]["data"]
        )
    return computed_data


def main(force=False):
    time_dirs = process_openfoam_solution(force=False)
    for time in tqdm(time_dirs, file=sys.stdout):
        if time == "0":
            continue
        pickle_filepath = Path(f"./computed_data_{time}.p")
        if force or not pickle_filepath.is_file():
            state_data = load_timestep(time)
            rate_data = compute_rates(state_data)
            write_timestep_pickle(pickle_filepath, time, rate_data, force=True)
        pickle_to_openfoam(pickle_filepath, Path(".") / time, auto_merge=True)
    return time_dirs


if __name__ == "__main__":
    time_dirs = main(force=False)
