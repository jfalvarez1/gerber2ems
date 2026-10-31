# Boundary-condition investigation — not a validated release

The `fix/absorbing-boundary-validation` branch is experimental. Stable `main`
contains output-retention and packaging improvements. The boundary change is
held here because both tested fixtures reached the time-step cap.

## What was run

Antmicro's `stub_short` and `stub_long` examples at upstream revision
`1d4dc55cc47590a29444af96a87d3cdd26a871fa`, with `sim_length=10` and one openEMS
worker. Control runs used the original simulation-stage PEC default, with both
ports excited sequentially. Experimental runs used eight-cell PML on all faces.
Their forward excitation finished at the time-step cap; the reverse excitation
was deliberately stopped after saving the forward waves. Published fixture VNA
files contain S11, not a measured full two-port matrix.

The Linux build used openEMS-Project v0.37.0
(`974294ba7d812ef5a46a4760593057aee7ce6866`), openEMS
`305df56aa7df4d2f18c687083f484a96f9a22610`, and CSXCAD
`c46e3206f20027b0b4605c797d07bddab76de942`. Ubuntu 24.04, Python 3.12.
Every retained run has its exact command, source commit/diff, input hashes and
package versions in `run-manifest.json`. A parent return code of -15 describes
the intentionally interrupted reverse run; `first-port-capture.json` separately
records the completed forward excitation. It does not turn a capped run into a
converged result.

## Reproduce the comparison

Keep each run in a separate copied fixture directory. Install the native stack
following the [openEMS build instructions](https://docs.openems.de/install.html)
and this project's installation instructions. Build Python bindings against the
same native installation: CSXCAD uses `CSXCAD_INSTALL_PATH`; openEMS uses
`OPENEMS_INSTALL_PATH` plus `CSXCAD_INSTALL_PATH`.

With this fork installed and a copied example as the working directory:

```console
gerber2ems --all --threads 1 --boundary PML_8
```

Do not use `--overwrite` to erase controls. For the recorded PML run, only the
first excitation is available. `first-port-waves.npz` has NaN in the missing
column, not zero. The normal CLI `port-waves.npz` can also be compared directly.

From the repository root, with NumPy and Matplotlib installed:

```console
python -m unittest discover -s validation -p test_comparison.py -v
python validation/compare_fixture.py --before /path/control --after /path/experiment --vna examples/stub_short/vna.csv --output /path/new-report
```

The output directory must not exist. The comparison archives raw waves,
configuration, geometry and logs; exports complex values and errors to CSV;
and produces annotated SVG/PNG plots. It uses linear real/imaginary interpolation
only within overlapping measured frequencies. There is no smoothing, fitting,
phase rotation or calibration adjustment. Full-matrix `B = S A` diagnostics
require every excitation; the S11 overlay uses upstream's per-excitation ratio.

## Recorded diagnostic results

| Fixture | PEC complex S11 RMSE | PML complex S11 RMSE | Accepted? |
| --- | ---: | ---: | --- |
| Short stub | 0.112105 | 0.122448 | No: both capped |
| Long stub | 0.123969 | 0.111917 | No: both capped |

These dimensionless errors use 655 overlapping VNA points, 0.2–4 GHz. The
published VNA file extends to 6 GHz; no simulated agreement above 4 GHz is
claimed. PML improved energy decay but did not consistently improve measured
agreement. Explicit MUR experiments diverged to nonfinite energy and are rejected.
The branch now raises on that native diagnostic rather than publishing plots as
successful output.

The model uses perfect conductor copper and epsilon-only dielectric. The
imported `lossTangent` field is not applied by the current material builder.
Connector/reference-plane treatment, PML spacing, mesh convergence and material
loss need further investigation. A lower error or passive matrix alone is not a
validation certificate. Do not teach these results as a verified board design.

References: [Antmicro's measurement study](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow/),
[test board](https://openhardware.antmicro.com/boards/si-simulation-test-board/),
[openEMS boundaries](https://docs.openems.de/en/stable/concepts/bc.html),
[native stopping diagnostics](https://docs.openems.de/en/latest/faq.html).
