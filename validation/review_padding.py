"""Combine independent excitations and quantify boundary sensitivity without fitting."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_fixture import run_data


def collect(forward, reverse):
    """Require the identical model, geometry, frequency grid and reference impedances."""
    for relative in ("ems/geometry/geometry.xml", "simulation.json"):
        if (forward / relative).read_bytes() != (reverse / relative).read_bytes():
            raise ValueError(f"Cannot combine excitations from different models: {relative}")
    paths = (forward / "first-port-waves.npz", reverse / "excitation-waves.npz")
    with np.load(paths[0], allow_pickle=False) as first, np.load(paths[1], allow_pickle=False) as second:
        for key in ("frequency_hz", "reference_ohm"):
            if not np.array_equal(first[key], second[key]):
                raise ValueError(f"Mismatched {key}")
        data = {key: first[key].copy() for key in first.files}
        for key in ("incident", "reflected"):
            expected = (2, 2, len(data["frequency_hz"]))
            if first[key].shape != expected or second[key].shape != expected:
                raise ValueError("Expected two-port waves in [port, excitation, frequency] order")
            data[key][:, 1, :] = second[key][:, 1, :]
            if not np.isfinite(data[key]).all():
                raise ValueError("Each requested excitation must contain finite waves")
    return data


def archive_run(source, destination, waves):
    """Copy selected small reproducibility files, never the full temporary FDTD dump."""
    destination.mkdir(parents=True)
    for name in (
        "run.log",
        "run-manifest.json",
        "simulation.json",
        "domain-before.json",
        "domain-after.json",
        "run_boundary_case.py",
        "audit_domain.py",
    ):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)
    shutil.copy2(source / "ems/geometry/geometry.xml", destination / "geometry.xml")
    shutil.copy2(source / waves, destination / "port-waves.npz")


def main():
    """Publish raw two-port waves, diagnostics and annotated plots to a new directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("forward", "reverse", "larger", "capped", "vna", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory")
    waves = collect(args.forward, args.reverse)
    args.output.mkdir(parents=True)
    network = args.output / "network"
    (network / "ems/simulation").mkdir(parents=True)
    np.savez_compressed(network / "ems/simulation/port-waves.npz", **waves)
    logs = [(root / "run.log").read_text() for root in (args.forward, args.reverse)]
    (network / "run.log").write_text("\n".join(logs))
    frequency, _, matrix, _, metrics = run_data(network)
    base_f, base_ratio, _, energy, base_metrics = run_data(args.forward)
    large_f, large_ratio, _, large_energy, large_metrics = run_data(args.larger)
    capped_f, capped_ratio, _, capped_energy, capped_metrics = run_data(args.capped)
    np.testing.assert_array_equal(base_f, large_f)
    np.testing.assert_array_equal(base_f, frequency)
    delta = large_ratio[:, :, 0] - base_ratio[:, :, 0]
    vna = np.loadtxt(args.vna, delimiter=",", skiprows=1)
    measured_f, measured = vna[:, 0] * 1e6, vna[:, 1] + 1j * vna[:, 2]
    mask = (measured_f >= frequency[0]) & (measured_f <= frequency[-1])
    interp = np.interp(measured_f[mask], frequency, matrix[:, 0, 0].real)
    interp = interp + 1j * np.interp(measured_f[mask], frequency, matrix[:, 0, 0].imag)
    report = {
        "model": "Antmicro stub_short Gerber slice; PEC copper and epsilon-only dielectric",
        "interpretation": "Numerical diagnostics, not hardware validation or EMC compliance",
        "matrix_method": "Power-wave normalization with real Z0; solve B = S A; no passivity enforcement",
        "two_port": metrics,
        "boundary_max_complex_S11_change": float(abs(delta[:, 0]).max()),
        "boundary_max_complex_S21_change": float(abs(delta[:, 1]).max()),
        "full_matrix_S11_complex_rmse_to_published_VNA": float(np.sqrt(np.mean(abs(interp - measured[mask]) ** 2))),
        "comparison_points": int(mask.sum()),
        "forward_run": base_metrics,
        "larger_run": large_metrics,
        "old_capped_run": capped_metrics,
        "vna_sha256": hashlib.sha256(args.vna.read_bytes()).hexdigest(),
        "unresolved": [
            "No local-mesh convergence study",
            "No copper/dielectric-loss model",
            "Connector and measurement reference-plane uncertainty",
            "R4 zero-ohm link appears in placement CSV but has no model; measured population unknown",
        ],
    }
    for label, source, name in (
        ("forward", args.forward, "first-port-waves.npz"),
        ("reverse", args.reverse, "excitation-waves.npz"),
        ("larger", args.larger, "first-port-waves.npz"),
        ("capped", args.capped, "first-port-waves.npz"),
    ):
        archive_run(source, args.output / label, name)
    shutil.copy2(args.vna, args.output / "published-vna.csv")
    columns = [frequency]
    headings = ["frequency_hz"]
    for i, j in ((0, 0), (1, 0), (0, 1), (1, 1)):
        columns.extend((matrix[:, i, j].real, matrix[:, i, j].imag))
        headings.extend((f"S{i + 1}{j + 1}_real", f"S{i + 1}{j + 1}_imag"))
    np.savetxt(
        args.output / "two-port.csv", np.column_stack(columns), delimiter=",", comments="", header=",".join(headings)
    )
    np.savetxt(
        args.output / "boundary-change.csv",
        np.column_stack((frequency, abs(delta[:, 0]), abs(delta[:, 1]))),
        delimiter=",",
        comments="",
        header="frequency_hz,absolute_complex_S11_change,absolute_complex_S21_change",
    )
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(11, 11), layout="constrained")
    axes[0].plot(
        measured_f / 1e9,
        20 * np.log10(np.maximum(abs(measured), 1e-9)),
        color="#555d67",
        label="Published VNA S11 (Antmicro)",
    )
    axes[0].plot(
        frequency / 1e9, 20 * np.log10(abs(matrix[:, 0, 0])), color="#007d8a", label="Padded model S11, full B = S A"
    )
    axes[0].plot(
        frequency / 1e9, 20 * np.log10(abs(matrix[:, 1, 0])), color="#7048a8", label="Padded model S21, simulated only"
    )
    axes[0].set(xlabel="Frequency (GHz)", ylabel="Magnitude (dB)", title="Residual measurement mismatch remains")
    axes[0].axvspan(4, 6, color="#ddd", alpha=0.5)
    axes[0].text(4.15, -25, "No simulation\nabove 4 GHz", va="top", bbox={"facecolor": "white", "edgecolor": "#aaa"})

    def status(values):
        return "criterion reached" if values["time_domain_stop_reached"] else "NOT converged"

    for values, label, color in (
        (capped_energy, f"Original PML domain: {status(capped_metrics)}", "#aa5626"),
        (energy, f"+10 outer cells: {status(base_metrics)}", "#007d8a"),
        (large_energy, f"+14 outer cells: {status(large_metrics)}", "#7048a8"),
    ):
        axes[1].plot(values[:, 0], values[:, 2], color=color, label=label)
    axes[1].axhline(-60, color="#555d67", ls="--", label="−60 dB stopping criterion")
    axes[1].set(
        xlabel="FDTD time step",
        ylabel="Native field energy (dB)",
        title="Same board and local mesh; boundary moved into surrounding vacuum",
    )
    axes[2].plot(frequency / 1e9, abs(delta[:, 0]), color="#007d8a", label="|ΔS11|, per-excitation ratio")
    axes[2].plot(frequency / 1e9, abs(delta[:, 1]), color="#7048a8", label="|ΔS21|, per-excitation ratio")
    axes[2].set(
        xlabel="Frequency (GHz)",
        ylabel="Absolute complex change",
        title="Remaining outer-domain sensitivity: +10 → +14 cells per face",
    )
    worst = np.argmax(abs(delta[:, 1]))
    axes[2].annotate(
        f"Maximum |ΔS21| = {abs(delta[worst, 1]):.6f}",
        xy=(frequency[worst] / 1e9, abs(delta[worst, 1])),
        xytext=(0.02, 0.85),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->"},
        bbox={"facecolor": "white", "edgecolor": "#a77d34"},
    )
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(loc="lower left", fontsize=8)
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle(
        "Native openEMS 0.37.0 · short physical stub fixture\nNumerical progress, not a validated board model",
        fontsize=14,
    )
    fig.savefig(args.output / "si-boundary-review.svg")
    fig.savefig(args.output / "si-boundary-review.png", dpi=140)
    plt.close(fig)
    (args.output / "review.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
