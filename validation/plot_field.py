"""Plot an actual openEMS frequency-domain E-field dump with geometry overlays."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    """Normalize only the display; retain complex raw data and dimensional metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory")
    with h5py.File(args.field, "r") as source:
        # HDF5_File_Writer::WriteRectMesh already applies mesh_scaling. Stored
        # Cartesian coordinates are metres; applying that attribute again is wrong.
        x, y, z = (source[f"Mesh/{a}"][:] * 1e3 for a in "xyz")
        data = source["FieldData/FD/f0"]
        if data.attrs["d_order"] != "NXYZ" or data.shape != (3, len(x), len(y), 1):
            raise ValueError("Expected a single XY plane in NXYZ order")
        frequency = float(data.attrs["frequency"])
        field = data[:]
    if not np.isfinite(field).all():
        raise ValueError("Nonfinite field dump")
    magnitude = np.sqrt(np.sum(abs(field[:, :, :, 0]) ** 2, axis=0))
    if magnitude.max() <= 0:
        raise ValueError("Zero field dump")
    relative_db = 20 * np.log10(np.maximum(magnitude / magnitude.max(), 1e-6))
    args.output.mkdir(parents=True)
    np.savez_compressed(
        args.output / "field-data.npz",
        x_mm=x,
        y_mm=y,
        z_mm=z,
        electric_field=field,
        relative_db=relative_db,
        frequency_hz=frequency,
    )
    root = ET.parse(args.geometry).getroot()
    unit_mm = float(root.find("RectilinearGrid").attrib["DeltaUnit"]) * 1e3
    fig, ax = plt.subplots(figsize=(13, 4.5), layout="constrained")
    plot = ax.pcolormesh(x, y, relative_db.T, vmin=-50, vmax=0, cmap="viridis", shading="nearest", rasterized=True)
    for polygon in root.findall("Properties/Metal[@Name='Gerber_0']/Primitives/Polygon"):
        points = np.array([[float(v.attrib["X1"]), float(v.attrib["X2"])] for v in polygon.findall("Vertex")]) * unit_mm
        if len(points):
            points = np.vstack((points, points[0]))
            ax.plot(points[:, 0], points[:, 1], color="white", lw=0.65, alpha=0.8)
    for name, label, target in (("Port_0", "Driven port 0", (5, 6.4)), ("Port_1", "Terminated port 1", (32, 6.4))):
        box = root.find(f"Properties/Metal[@Name='{name}']/Primitives/Box")
        ends = [np.array([float(box.find(p).attrib[a]) for a in "XY"]) * unit_mm for p in ("P1", "P2")]
        center = (ends[0] + ends[1]) / 2
        ax.annotate(
            label,
            xy=center,
            xytext=target,
            ha="center",
            color="#283544",
            arrowprops={"arrowstyle": "->", "color": "#d17623"},
            bbox={"facecolor": "white", "edgecolor": "#acb9c3"},
        )
    ax.set(
        xlabel="x (mm)",
        ylabel="y (mm)",
        aspect="equal",
        ylim=(-0.2, 7.3),
        title=f"Actual FDTD electric field at {frequency / 1e9:g} GHz · z = {z[0]:.3f} mm\n"
        "White outlines: imported top copper; color: |E| relative to this plane's peak",
    )
    fig.colorbar(plot, ax=ax, label="Relative field magnitude (dB)", shrink=0.75)
    fig.savefig(args.output / "electric-field.svg")
    fig.savefig(args.output / "electric-field.png", dpi=150)
    plt.close(fig)
    (args.output / "field-note.json").write_text(
        json.dumps(
            {
                "frequency_hz": frequency,
                "display": "20 log10(|E| / plane peak); not an absolute field-strength or EMC prediction",
                "source": str(args.field),
                "native_axis_order": "NXYZ",
                "z_mm": z.tolist(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
