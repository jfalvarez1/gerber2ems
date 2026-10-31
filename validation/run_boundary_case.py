"""Rerun saved geometry with vacuum padding; preserve the board and its local mesh.

This diagnostic is deliberately outside the production CLI. It writes a new run,
retains its native log and forward waves, and never overwrites its source.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from audit_domain import audit


def pad_geometry(source, destination, count):
    """Append exterior cells; every existing mesh coordinate remains unchanged."""
    tree = ET.parse(source)
    grid = tree.getroot().find("RectilinearGrid")
    for axis in "XYZ":
        element = grid.find(axis + "Lines")
        original = np.fromstring(element.text, sep=",")
        lower = original[0] - (original[1] - original[0]) * np.arange(count, 0, -1)
        upper = original[-1] + (original[-1] - original[-2]) * np.arange(1, count + 1)
        extended = np.concatenate((lower, original, upper))
        element.text = ",".join(format(x, ".17g") for x in extended)
        element.set("Qty", str(len(extended)))
    tree.write(destination, encoding="UTF-8", xml_declaration=True)


def worker(args):
    """Run one selected excitation with the same original Gaussian pulse."""
    os.chdir(args.output)
    # Constants bind to cwd, so import the application only after selecting the run.
    from gerber2ems import importer
    from gerber2ems.config import Config
    from gerber2ems.constants import GEOMETRY_FILE
    from gerber2ems.main import parse_arguments
    from gerber2ems.simulation import Simulation

    sys.argv = ["gerber2ems", "-s", "--threads", str(args.threads), "--boundary", "PML_8"]
    Config.load(args.output / "simulation.json", parse_arguments())
    cfg = Config()
    importer.import_stackup()
    importer.import_port_positions()
    sim = Simulation(GEOMETRY_FILE)
    sim.fdtd.SetNumberOfTimeSteps(args.steps)
    sim.fdtd.SetEndCriteria(1e-6)
    sim.set_excitation()
    sim.setup_ports(args.excitation)
    # Bounds come from the model's dielectric box, not from an assumed board size.
    geometry = audit(GEOMETRY_FILE)
    slab = next(p for p in geometry["properties"] if p["name"] == "Substrate_0")
    scale = 1e-3 / geometry["unit_m"]
    low, high = np.array(slab["min_mm"]) * scale, np.array(slab["max_mm"]) * scale
    low[2] = high[2] = (low[2] + high[2]) / 2
    if args.excitation == 0:
        field = sim.csx.AddDump("electric_xy", dump_type=10, dump_mode=2, file_type=1, frequency=[3e9])
        field.AddBox(low, high)
    sim.run(args.excitation)
    sim.add_ports()
    frequency = np.linspace(cfg.frequency.start, cfg.frequency.stop, 1001)
    reflected, incident = sim.get_port_parameters(args.excitation, frequency)
    a = np.full((len(cfg.all_ports), len(cfg.all_ports), len(frequency)), np.nan, complex)
    b = a.copy()
    a[:, args.excitation, :], b[:, args.excitation, :] = incident, reflected
    if not np.isfinite(incident).all() or not np.isfinite(reflected).all():
        raise ValueError("Nonfinite port waves; rejected")
    name = "first-port-waves.npz" if args.excitation == 0 else "excitation-waves.npz"
    np.savez_compressed(
        args.output / name,
        frequency_hz=frequency,
        incident=a,
        reflected=b,
        reference_ohm=np.array([p.impedance for p in cfg.all_ports]),
    )


def main():
    """Archive inputs, run a child with a retained log, and record termination status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--padding", type=int, default=10)
    parser.add_argument("--steps", type=int, default=120000)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--excitation", type=int, choices=(0, 1), default=0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.source, args.output = args.source.resolve(), args.output.resolve()
    if args.worker:
        worker(args)
        return
    if args.output.exists() or args.output.is_relative_to(args.source):
        parser.error("Choose a new run outside the source directory")
    if args.padding < 0 or args.steps <= 0 or args.threads <= 0:
        parser.error("Invalid padding, time-step cap or worker count")
    args.output.mkdir(parents=True)
    for name in ("run_boundary_case.py", "audit_domain.py"):
        shutil.copy2(Path(__file__).parent / name, args.output / name)
    shutil.copytree(args.source / "fab", args.output / "fab")
    for name in ("simulation.json", "input-original.json", "input-used.json"):
        shutil.copy2(args.source / name, args.output / name)
    (args.output / "ems/geometry").mkdir(parents=True)
    (args.output / "ems/simulation").mkdir()
    source = args.source / "ems/geometry/geometry.xml"
    destination = args.output / "ems/geometry/geometry.xml"
    pad_geometry(source, destination, args.padding)
    for name, path in (("before", source), ("after", destination)):
        (args.output / f"domain-{name}.json").write_text(json.dumps(audit(path), indent=2))
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--worker"]
    manifest = {
        "command": command,
        "padding_cells_per_face": args.padding,
        "time_step_cap": args.steps,
        "end_criterion": 1e-6,
        "source_geometry_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "geometry_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "excitation": "Original Gaussian, original frequency limits",
        "excitation_index": args.excitation,
        "model_changes": "Vacuum cells outside the original mesh; board geometry and local mesh unchanged",
    }
    start = time.monotonic()
    with (args.output / "run.log").open("w") as log:
        result = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "MPLBACKEND": "Agg", "OPENBLAS_NUM_THREADS": "1"},
        )
    manifest.update(return_code=result.returncode, elapsed_seconds=time.monotonic() - start)
    log = (args.output / "run.log").read_text()
    manifest["hit_step_limit"] = "Max. number of timesteps was reached" in log
    (args.output / "run-manifest.json").write_text(json.dumps(manifest, indent=2))
    if args.excitation == 0:
        shutil.copy2(args.output / "run.log", args.output / "first-port.log")
        (args.output / "first-port-capture.json").write_text(
            json.dumps(
                {
                    "excitation": 0,
                    "full_two_port": False,
                    "reason": "Only forward excitation requested; no invented reverse data",
                },
                indent=2,
            )
        )
    print(json.dumps(manifest, indent=2))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
