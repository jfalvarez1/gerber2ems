"""Compare saved fixture runs with published VNA S11, without fitting or smoothing.

python validation/compare_fixture.py --before RUN --after RUN --vna vna.csv --output NEW_DIR
The result is a diagnostic, not a calibration or validation certificate.
"""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def run_data(root):
    """Read retained waves; derive a full matrix only when all ports were excited."""
    wave_path = root / "first-port-waves.npz"
    partial = wave_path.exists()
    if not partial:
        wave_path = root / "ems/simulation/port-waves.npz"
    with np.load(wave_path, allow_pickle=False) as waves:
        frequency = waves["frequency_hz"]
        z0 = waves["reference_ohm"]
        if not np.isrealobj(z0) or not np.all(np.isfinite(z0) & (z0 > 0)):
            raise ValueError("Only real positive reference impedances are supported")
        if frequency.ndim != 1 or not np.isfinite(frequency).all() or np.any(np.diff(frequency) <= 0):
            raise ValueError("Simulation frequencies must be finite and strictly increasing")
        expected_shape = (len(z0), len(z0), len(frequency))
        if waves["incident"].shape != expected_shape or waves["reflected"].shape != expected_shape:
            raise ValueError("Wave arrays must use [measured port, excitation port, frequency]")
        incident = np.moveaxis(waves["incident"], 2, 0) / np.sqrt(z0)[None, :, None]
        reflected = np.moveaxis(waves["reflected"], 2, 0) / np.sqrt(z0)[None, :, None]
    if not np.isfinite(incident[:, :, 0]).all() or not np.isfinite(reflected[:, :, 0]).all():
        raise ValueError("Finite first-excitation data are required")
    complete = np.isfinite(incident).all() and np.isfinite(reflected).all()
    if np.any(np.abs(incident[:, 0, 0]) == 0):
        raise ValueError("First excitation has zero incident reference wave")
    scale = np.max(np.abs(incident), axis=1, keepdims=True)
    if np.any(scale == 0):
        raise ValueError("Unexcited matrix column")
    scale = np.where(np.isfinite(scale), scale, 1.0)
    incident, reflected = incident / scale, reflected / scale
    matrix, condition = None, None
    if complete:
        condition = np.linalg.cond(incident)
        if not np.isfinite(condition).all() or condition.max() > 1e10:
            raise ValueError("Ill-conditioned incident-wave matrix")
        matrix = np.linalg.solve(incident.swapaxes(1, 2), reflected.swapaxes(1, 2)).swapaxes(1, 2)
    ratio = np.full_like(reflected, np.nan)
    for excitation in range(incident.shape[2]):
        reference = incident[:, excitation, excitation]
        if np.isfinite(reference).all() and np.all(np.abs(reference) > 0):
            ratio[:, :, excitation] = reflected[:, :, excitation] / reference[:, None]
    log = (root / ("first-port.log" if partial else "run.log")).read_text()
    samples = []
    previous = -1
    for match in re.finditer(
        r"Timestep:\s*(\d+).*?Energy:\s*~\s*([\d.eE+-]+|inf|nan)\s*\(\s*([+-]?\s*[\d.eE+-]+)dB\)", log
    ):
        step, energy = int(match[1]), float(match[2])
        if step < previous:
            break  # Plot the first excitation only; never join separate decays.
        samples.append((step, energy, float(match[3].replace(" ", ""))))
        previous = step
    divergent = bool(re.search(r"Energy:\s*~\s*[+-]?(?:inf|nan)\b", log, re.IGNORECASE))
    capped = "Max. number of timesteps was reached" in log
    metrics = {
        "nonfinite_energy": divergent,
        "hit_step_limit": capped,
        "full_matrix_available": bool(complete),
        "time_domain_stop_reached": not divergent and not capped and "Time for " in log,
        "maximum_wave_condition": float(condition.max()) if complete else None,
        "maximum_singular_value_ratio": float(np.linalg.svd(ratio, compute_uv=False)[:, 0].max()) if complete else None,
        "maximum_singular_value_matrix": float(np.linalg.svd(matrix, compute_uv=False)[:, 0].max())
        if complete
        else None,
        "maximum_reciprocity_error": float(np.max(np.abs(matrix - matrix.swapaxes(1, 2)))) if complete else None,
        "wave_sha256": hashlib.sha256(wave_path.read_bytes()).hexdigest(),
    }
    return frequency, ratio, matrix, np.asarray(samples).reshape(-1, 3), metrics


def main():
    """Archive a boundary experiment and plot its measured-reference discrepancy."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "vna", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--before-label", default="Before")
    parser.add_argument("--after-label", default="After")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; existing evidence is not overwritten")
    runs = {label: run_data(root) for label, root in (("Before", args.before), ("After", args.after))}
    vna = np.loadtxt(args.vna, delimiter=",", skiprows=1)
    measured_f, measured_s11 = vna[:, 0] * 1e6, vna[:, 1] + 1j * vna[:, 2]
    if not np.isfinite(vna).all() or np.any(np.diff(measured_f) <= 0):
        raise ValueError("VNA data must be finite and frequencies strictly increasing")
    args.output.mkdir(parents=True)
    shutil.copy2(args.vna, args.output / "published-vna.csv")
    report = {
        "comparison": "Raw complex S11; linear interpolation onto overlapping VNA frequencies; no fitting or smoothing",
        "vna_sha256": hashlib.sha256(args.vna.read_bytes()).hexdigest(),
        "runs": {},
    }
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(11, 9), layout="constrained")
    axes[0].plot(
        measured_f / 1e9,
        20 * np.log10(np.maximum(abs(measured_s11), 1e-7)),
        color="#3b4655",
        lw=2,
        label="Published VNA S11 (Antmicro)",
    )
    largest_error = 0.0
    for label, color in (("Before", "#b56b28"), ("After", "#007d8a")):
        frequency, ratio, matrix, energy, metrics = runs[label]
        mask = (measured_f >= frequency[0]) & (measured_f <= frequency[-1])
        f = measured_f[mask]
        simulation = np.interp(f, frequency, ratio[:, 0, 0].real) + 1j * np.interp(f, frequency, ratio[:, 0, 0].imag)
        error = abs(simulation - measured_s11[mask])
        largest_error = max(largest_error, float(error.max()))
        metrics.update(
            comparison_points=int(mask.sum()),
            complex_s11_rmse=float(np.sqrt(np.mean(error**2))),
            complex_s11_max_error=float(error.max()),
        )
        report["runs"][label] = metrics
        status = "time-domain stop reached" if metrics["time_domain_stop_reached"] else "NOT converged / rejected"
        axes[0].plot(
            frequency / 1e9,
            20 * np.log10(np.maximum(abs(ratio[:, 0, 0]), 1e-7)),
            color=color,
            lw=1.6,
            label=f"{args.before_label if label == 'Before' else args.after_label} — {status}",
        )
        axes[1].plot(f / 1e9, error, color=color, label=f"{label}: complex RMSE {metrics['complex_s11_rmse']:.3f}")
        np.savetxt(
            args.output / (label.lower() + "-comparison.csv"),
            np.column_stack(
                [f, simulation.real, simulation.imag, measured_s11[mask].real, measured_s11[mask].imag, error]
            ),
            delimiter=",",
            comments="",
            header="frequency_hz,sim_S11_re,sim_S11_im,vna_S11_re,vna_S11_im,complex_absolute_error",
        )
        archive = args.output / label.lower()
        archive.mkdir()
        source = args.before if label == "Before" else args.after
        for name in (
            "run.log",
            "run-manifest.json",
            "input-original.json",
            "input-used.json",
            "simulation.json",
            "first-port.log",
            "first-port-capture.json",
        ):
            if (source / name).exists():
                shutil.copy2(source / name, archive / name)
        wave_path = source / "first-port-waves.npz"
        if not wave_path.exists():
            wave_path = source / "ems/simulation/port-waves.npz"
        shutil.copy2(wave_path, archive / "port-waves.npz")
        shutil.copy2(source / "ems/geometry/geometry.xml", archive / "geometry.xml")
        for csv in (source / "ems/simulation").glob("Sx*.csv"):
            shutil.copy2(csv, archive / csv.name)
    axes[0].set(
        ylabel="S11 magnitude (dB)",
        xlabel="Frequency (GHz)",
        title="Recorded per-excitation S11 vs published measurement",
    )
    axes[1].set(
        ylabel="|S11 simulated − S11 measured|",
        xlabel="Frequency (GHz)",
        title="Complex error includes phase; lower is closer",
    )
    axes[1].set_ylim(0, max(largest_error * 1.4, 0.01))
    worst = np.argmax(error)
    axes[1].axvspan(f[worst] / 1e9 - 0.05, f[worst] / 1e9 + 0.05, color="#efbe62", alpha=0.3)
    axes[1].annotate(
        f"Largest after-run discrepancy\n{f[worst] / 1e9:.2f} GHz: {error[worst]:.3f}",
        xy=(f[worst] / 1e9, error[worst]),
        xytext=(0.04, 0.85),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->"},
        bbox={"facecolor": "white", "edgecolor": "#bd9246"},
    )
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9, loc="lower right")
    fig.suptitle(
        "Antmicro PCB stub fixture — boundary-condition experiment\nPublished VNA reference is not a local measurement",
        fontsize=14,
    )
    fig.savefig(args.output / "vna-comparison.svg")
    fig.savefig(args.output / "vna-comparison.png", dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 5.5), layout="constrained")
    for label, color in (("Before", "#b56b28"), ("After", "#007d8a")):
        energy = runs[label][3]
        valid = np.isfinite(energy[:, 2])
        ax.plot(energy[valid, 0], energy[valid, 2], color=color, label=label, lw=2)
    ax.axhspan(-60, 2, color="#efbe62", alpha=0.1)
    ax.axhline(-60, color="#a24c20", linestyle="--", label="Nominal −60 dB energy criterion")
    ax.set(
        xlabel="FDTD time step (first excitation)",
        ylabel="Solver-reported energy (dB)",
        title="Energy decay diagnostic — native progress samples, first excitation only",
    )
    ax.grid(alpha=0.2)
    ax.legend()
    fig.savefig(args.output / "energy-decay.svg")
    fig.savefig(args.output / "energy-decay.png", dpi=140)
    plt.close(fig)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
