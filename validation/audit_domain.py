"""Read CSXCAD geometry and report occupied bounds against eight-cell PML faces."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


def audit(path, cells=8):
    """Report dimensional clearances; an overlap is evidence to inspect, not a verdict."""
    root = ET.parse(path).getroot()
    grid = root.find("RectilinearGrid")
    unit = float(grid.attrib["DeltaUnit"])
    axes = [np.fromstring(grid.find(axis + "Lines").text, sep=",") for axis in "XYZ"]
    if any(len(axis) <= 2 * cells for axis in axes):
        raise ValueError("Not enough mesh lines for an interior between PML faces")
    inner_min = np.array([axis[cells] for axis in axes])
    inner_max = np.array([axis[-cells - 1] for axis in axes])
    properties = []
    for prop in root.findall("Properties/*"):
        points = []
        unsupported = []
        for primitive in prop.findall("Primitives/*"):
            if primitive.tag == "Box":
                for name in ("P1", "P2"):
                    p = primitive.find(name)
                    points.append([float(p.attrib[a]) for a in "XYZ"])
            elif primitive.tag in ("Polygon", "LinPoly"):
                direction = int(primitive.attrib["NormDir"])
                elevation = float(primitive.attrib["Elevation"])
                length = float(primitive.attrib.get("Length", 0))
                for vertex in primitive.findall("Vertex"):
                    for z in (elevation, elevation + length):
                        p = [0.0, 0.0, 0.0]
                        p[direction] = z
                        p[(direction + 1) % 3] = float(vertex.attrib["X1"])
                        p[(direction + 2) % 3] = float(vertex.attrib["X2"])
                        points.append(p)
            else:
                unsupported.append(primitive.tag)
        if points:
            low, high = np.min(points, axis=0), np.max(points, axis=0)
            clearance = np.minimum(low - inner_min, inner_max - high) * unit * 1e3
            properties.append(
                {
                    "name": prop.attrib.get("Name"),
                    "type": prop.tag,
                    "min_mm": (low * unit * 1e3).tolist(),
                    "max_mm": (high * unit * 1e3).tolist(),
                    "clearance_to_PML_mm": clearance.tolist(),
                    "overlaps_PML_axes": [a for a, value in zip("xyz", clearance, strict=True) if value < 0],
                    "unhandled_primitives": unsupported,
                }
            )
    return {
        "unit_m": unit,
        "mesh_lines": [len(a) for a in axes],
        "cells": int(np.prod([len(a) - 1 for a in axes])),
        "interior_min_mm": (inner_min * unit * 1e3).tolist(),
        "interior_max_mm": (inner_max * unit * 1e3).tolist(),
        "properties": properties,
    }


def main():
    """Print a read-only geometry audit as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.geometry), indent=2))


if __name__ == "__main__":
    main()
