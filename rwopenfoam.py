#!/usr/bin/env python
import pickle
import argparse
import textwrap
import typing
from pathlib import Path

import numpy as np
import numpy.typing as npt
from tqdm import tqdm


def _list_to_dimensions(dimargs: list[str]) -> list[int]:
    if len(dimargs) != 7:
        raise ValueError(
            f"The dimensions string does not have 7 components: {dimargs}"
        )
    dimensions = []
    for dim in dimargs:
        if "[" in dim:
            dimensions.append(int(dim.split("[")[-1]))
        elif "]" in dim:
            dimensions.append(int(dim.split("]")[0]))
        else:
            dimensions.append(int(dim))
    return dimensions


def _dimensions_to_str(dimensions: list[int]) -> str:
    return str(dimensions).replace(",", "")


def _sanitize_uniform_value(args: list[str]) -> float | tuple[float]:
    if len(args) == 1:
        # Just need to remove the trailing semicolon
        return float(args[0].split(";")[0])
    elif len(args) == 3:
        # Process everything in between the parens and return a tuple
        return (
            float(args[0].split("(")[-1]),
            float(args[1]),
            float(args[2].split(")")[0]),
        )


def read_variable(file_path: Path) -> dict[str, typing.Any]:
    data: dict[str, typing.Any] = {
        "type": None,
        "dimensions": None,
        "data": [],
    }
    found_values_start = False
    num_values = None
    with open(file_path, "r") as infile:
        for line in infile:
            match line.split():
                case ["class", field_type]:
                    data["type"] = field_type[:-1]  # remove trailing semicolon
                case ["dimensions", *args]:
                    data["dimensions"] = _list_to_dimensions(args)
                case ["internalField", "uniform", *args]:
                    data["data"] = _sanitize_uniform_value(args)
                    return data
                case ["internalField", "nonuniform", *_]:
                    # Found the start of the internalField
                    # It is not a uniform field
                    # Break out of this loop and process the values
                    break
        for line in infile:
            match line.split():
                case [num] if not found_values_start and num_values is None:
                    num_values = int(num)
                case ["("]:
                    found_values_start = True
                case [")"] if found_values_start:
                    assert len(data["data"]) == num_values
                    break
                case [value] if found_values_start:
                    data["data"].append(float(value))
                case [vx, vy, vz] if found_values_start:
                    data["data"].append(
                        (
                            float(vx.split("(")[-1]),
                            float(vy),
                            float(vz.split(")")[0]),
                        )
                    )
    data["data"] = np.array(data["data"])
    return data


def read_species_list(kinetic_model_filepath: Path) -> list[str]:
    found_species_list = False
    num_species = None
    species_list: list[str] = []
    with open(kinetic_model_filepath, 'r') as kmfile:
        for line in kmfile:
            line = line.strip()
            if line == 'species':
                found_species_list = True
            elif found_species_list:
                if not num_species:
                    num_species = int(line)
                elif line == '(':
                    continue
                elif line in [')', ');']:
                    break
                else:
                    species_list.append(line)
    return species_list


def openfoam_to_pickle(
    timestamp: Path,
    pickle_filepath: Path,
    kinetic_model_filepath: typing.Optional[Path] = None,
    include_computed_quantities: bool = False,
    force: bool = False,
) -> None:
    solution: dict[str, npt.NDArray[np.float64] | float] = {}
    # Get the list of species from the kinetic model
    # This is done so that the species names can be prepended with a Y_
    # This is useful for future scripts that want to extract the species and so
    # can look for a common prefix
    if kinetic_model_filepath:
        species_list = read_species_list(kinetic_model_filepath)
    else:
        species_list = []
    # Load the data from the timestamp
    for var_file in timestamp.iterdir():
        if var_file.is_dir():
            continue
        var = var_file.name
        if var.endswith("_computed") and not include_computed_quantities:
            continue
        if species_list and var in species_list:
            var = f"Y_{var}"
        solution[var] = read_variable(var_file)
    if not force and pickle_filepath.exists():
        raise FileExistsError(f"{pickle_filepath} already exists.")
    with open(pickle_filepath, "wb") as pfile:
        pickle.dump(solution, pfile)


def _write_openfoam_var_file(
    filepath: Path,
    var: str,
    values: dict[str, typing.Any],
):
    timestamp = filepath.parent.name
    if values["type"] in ["volScalarField", "surfaceScalarField"]:
        data_type = "scalar"
    elif values["type"] in ["volVectorField"]:
        data_type = "vector"
    else:
        raise ValueError(
            f"Unknown data type {values['type']} for variable {var}"
        )
    with open(filepath, "w") as outfile:
        # Write the header
        outfile.write(
            textwrap.dedent(
                f"""\
                FoamFile
                {{
                    version         2.0;
                    format          ascii;
                    arch            "LSB;label=32;scalar=64;";
                    class           {values['type']};
                    location        "{timestamp}";
                    object          {var};
                }}
                // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

                dimensions      {_dimensions_to_str(values['dimensions'])};

                """
            )
        )
        # Write the data
        if isinstance(values["data"], float):
            outfile.write(f"internalField   uniform {values['data']};\n\n")
        elif isinstance(values["data"], tuple):
            uniform_vector_value = str(values["data"]).replace(",", "")
            outfile.write(
                f"internalField   uniform {uniform_vector_value};\n\n"
            )
        elif isinstance(values["data"], np.ndarray):
            outfile.write(f"internalField   nonuniform List<{data_type}>\n")
            outfile.write(f"{len(values['data'])}\n")
            outfile.write("(\n")
            for v in values["data"]:
                if isinstance(v, np.ndarray):
                    v = f"({v[0]} {v[1]} {v[2]})"
                else:
                    v = str(v)
                outfile.write(f"{v}\n")
            outfile.write(")\n;\n\n")
        # Write the footer
        zero_value = "(0 0 0)" if data_type == "vector" else 0
        outfile.write(
            textwrap.dedent(
                f"""\
                boundaryField
                {{
                    fuel
                    {{
                        type        calculated;
                        value       uniform {zero_value};
                    }}
                    air
                    {{
                        type        calculated;
                        value       uniform {zero_value};
                    }}
                    outlet
                    {{
                        type        calculated;
                        value       uniform {zero_value};
                    }}
                    frontAndBack
                    {{
                        type        empty;
                    }}
                }}
                """
            )
        )


def pickle_to_openfoam(
    solution_pickle: Path,
    timestamp: Path,
    auto_merge: bool = False,
) -> None:
    with open(solution_pickle, "rb") as pfile:
        data = pickle.load(pfile)
    if timestamp.is_dir():
        if not auto_merge:
            print(
                f"The directory {timestamp} already exists. "
                "Would you like to merge the loaded solution in?"
            )
            response = input("[y|N]: ")
            if response.lower() not in ["y", "yes"]:
                return
    else:
        timestamp.mkdir()
    for var, values in data.items():
        if (timestamp / var).is_file():
            print(f"{var} already exists in {timestamp}. Skipping.")
            continue
        _write_openfoam_var_file(timestamp / var, var, values)


def pickle_all_openfoam_times(
        case_dir: Path,
        kinetic_model_filepath: Path,
        include_computed_quantities: bool = False,
        pickle_filepath_prefix: str = "ofsolution_",
        force: bool = False,
        ):
    # Create a list of the time directories that need to be processed
    time_dirs = []
    for time_dir in case_dir.iterdir():
        pass
    # Skip any non-time directories and other files
        if not time_dir.is_dir():
            continue
        try:
            float(time_dir.name)
        except ValueError:
            continue
        time_dirs.append(time_dir)
    # Sort the time directories in numerical order
    time_dirs.sort(key=lambda p: float(p.name))
    # Process all the time directories
    for time_dir in tqdm(time_dirs):
        pickle_filepath = (
                case_dir / f"{pickle_filepath_prefix}{time_dir.name}.p"
                )
        if pickle_filepath.is_file() and not force:
            continue
        else:
            openfoam_to_pickle(
                    timestamp=time_dir,
                    pickle_filepath=pickle_filepath,
                    kinetic_model_filepath=kinetic_model_filepath,
                    include_computed_quantities=include_computed_quantities,
                    force=force,
                    )


def main() -> None:

    parser = argparse.ArgumentParser(
            prog='rwopenfoam',
            description='Convert between OpenFOAM and pickle files',
            )
    parser.add_argument(
            '--case-dir',
            type=Path,
            default=Path('.'),
            help='the OpenFOAM case directory',
            )
    subparsers = parser.add_subparsers(title='subcommands', dest='command')

    parser_of2p = subparsers.add_parser(
            'of2p',
            help='Convert from OpenFOAM to pickle',
            )
    parser_of2p.add_argument('timestamp', help='the timestamp to process')
    parser_of2p.add_argument(
            'pickle',
            help='the pickle file to write to or the pickle prefix if timestamp is "all"',
            )
    parser_of2p.add_argument(
            '-k',
            '--kinetics',
            help='the kinetic model to extract species from',
            )
    parser_of2p.add_argument(
            '-c',
            '--include-computed',
            help='include computed quantities',
            action='store_true',
            )
    parser_of2p.add_argument(
            '-f',
            '--force',
            help='overwrite pickle file if it already exists',
            action='store_true',
            )

    parser_p2of = subparsers.add_parser(
            'p2of',
            help='Convert from pickle to OpenFOAM',
            )
    parser_p2of.add_argument('pickle', help='the pickle file to read')
    parser_p2of.add_argument('timestamp', help='the timestamp to write to or "all"')
    parser_p2of.add_argument(
            '-m',
            '--merge',
            help='merge with directory if directory already exists',
            action='store_true',
            )

    args = parser.parse_args()

    if args.command == 'of2p':
        if args.kinetics:
            kinetic_model_filepath = args.case_dir / args.kinetics
        else:
            kinetic_model_filepath = None
        if args.timestamp == 'all':
            pickle_all_openfoam_times(
                    case_dir=args.case_dir,
                    kinetic_model_filepath=kinetic_model_filepath,
                    include_computed_quantities=args.include_computed,
                    pickle_filepath_prefix=args.pickle,
                    force=args.force,
                    )
        else:
            timestamp = args.case_dir / args.timestamp
            pickle_filepath = args.case_dir / args.pickle
            openfoam_to_pickle(
                    timestamp=timestamp,
                    pickle_filepath=pickle_filepath,
                    kinetic_model_filepath=kinetic_model_filepath,
                    include_computed_quantities=args.include_computed,
                    force=args.force,
                    )
    elif args.command == 'p2of':
        timestamp = args.case_dir / args.timestamp
        pickle_filepath = args.case_dir / args.pickle
        pickle_to_openfoam(
                solution_pickle=pickle_filepath,
                timestamp=timestamp,
                auto_merge=args.merge,
                )
    else:
        raise ValueError(f'Unknown command {args.command}')


if __name__ == "__main__":
    main()
