import pickle
import textwrap
import typing
from pathlib import Path

import numpy as np
import numpy.typing as npt


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
