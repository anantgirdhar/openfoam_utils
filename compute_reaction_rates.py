#!/usr/bin/env python
import pickle
import argparse
import textwrap
from pathlib import Path

import cantera as ct
import numpy as np
from tqdm import tqdm


def _write_timestep_pickle(pickle_filepath, timestamp, solution, force=False):
    if not force and pickle_filepath.is_file():
        raise FileExistsError(f"{pickle_filepath} already exists.")
    with open(pickle_filepath, "wb") as pfile:
        pickle.dump(solution, pfile)


def _get_value(ofdata, var, index):
    try:
        iter(ofdata[var]["data"])
    except TypeError:
        # This is not iterable
        # It is probably a uniform value
        return ofdata[var]["data"]
    else:
        return ofdata[var]["data"][index]


def _verify_OF_cantera_consistency(ofdata):
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


def _compute_rates(ofdata):
    _verify_OF_cantera_consistency(ofdata)
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
        T = _get_value(ofdata, "T", i)
        p = _get_value(ofdata, "p", i)
        Y = np.array([_get_value(ofdata, sp, i) for sp in cantera_species])
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


def compute_and_write_rate_data(
        *,
        state_data_pickle: Path,
        rate_data_pickle: Path,
        force: bool = False,
        ) -> None:
    if rate_data_pickle.is_file() and not force:
        raise FileExistsError(f'{rate_data_pickle} already exists.')
    with open(state_data_pickle, 'rb') as pfile:
        state_data = pickle.load(pfile)
    rate_data = _compute_rates(state_data)
    with open(rate_data_pickle, 'wb') as pfile:
        pickle.dump(rate_data, pfile)


def compute_and_write_all_rate_data(
        *,
        case_dir: Path,
        state_data_pickle_prefix: str,
        rate_data_pickle_prefix: str,
        force: bool = False,
        ) -> None:
    # Create a list of the time directories that need to be processed
    for state_data_pickle in tqdm(sorted(
            case_dir.glob(f'{state_data_pickle_prefix}*.p'),
            key=lambda p: float(p.stem.split('_')[-1]),
            )):
        rate_data_pickle = state_data_pickle.with_stem(
                state_data_pickle.stem.replace(
                    state_data_pickle_prefix,
                    rate_data_pickle_prefix,
                    )
                )
        # Skip the 0 time
        if state_data_pickle.stem == f'{state_data_pickle_prefix}0':
            continue
        if rate_data_pickle.is_file() and not force:
            continue
        compute_and_write_rate_data(
                state_data_pickle=state_data_pickle,
                rate_data_pickle=rate_data_pickle,
                )


def main() -> None:

    parser = argparse.ArgumentParser(
            prog='compute_reaction_rates',
            description='Compute reaction rates using Cantera',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )
    parser.add_argument(
            '--case-dir',
            type=Path,
            default=Path('.'),
            help='the OpenFOAM case directory',
            )
    parser.add_argument('timestamp', help='the timestamp to process or "all"')
    parser.add_argument(
            '-s',
            '--solution-pickle-prefix',
            default='ofsolution_',
            help='prefix of the pickle file containing the OpenFOAM solution',
            )
    parser.add_argument(
            '-r',
            '--rate-pickle-prefix',
            default='computed_',
            help='prefix of the pickle file to write computed rates to',
            )
    parser.add_argument(
            '-f',
            '--force',
            help='overwrite rate pickle if it already exists',
            action='store_true',
            )

    args = parser.parse_args()

    if args.timestamp == "all":
        compute_and_write_all_rate_data(
                case_dir=args.case_dir,
                state_data_pickle_prefix=args.solution_pickle_prefix,
                rate_data_pickle_prefix=args.rate_pickle_prefix,
                force=args.force,
                )
    else:
        state_data_pickle = (
                args.case_dir
                / f'{args.solution_pickle_prefix}{args.timestamp}.p'
                )
        rate_data_pickle = (
                args.case_dir / f'{args.rate_pickle_prefix}{args.timestamp}.p'
                )

        compute_and_write_rate_data(
                state_data_pickle=state_data_pickle,
                rate_data_pickle=rate_data_pickle,
                force=args.force,
                )


if __name__ == "__main__":
    main()
