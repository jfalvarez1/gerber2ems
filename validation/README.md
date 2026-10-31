# Boundary-condition investigation — not a validated release

The `fix/absorbing-boundary-validation` branch is experimental. Stable `main`
contains output-retention and packaging improvements. The boundary change is
held here because the original fixtures reached the time-step cap and the later
padded short-stub experiment still has unresolved measurement/model differences.

## Follow-up: preserve the local mesh and move PML off the board

`audit_domain.py` found the eight-cell PML overlapped the substrate and copper
in x/y and touched the copper faces in z. The interior z interval was only
−0.12 to 0 mm. `run_boundary_case.py` adds vacuum cells outside the original grid;
every original mesh coordinate, board primitive and Gaussian stimulus is kept.
It is a diagnostic tool, not a new production mesher or automatic accuracy fix.

With ten additional cells on every face, the forward excitation reached the
−60 dB stopping criterion in 37,694 steps instead of hitting the old 200,960-step
cap. The reverse excitation also completed. Fourteen additional cells reached
the same criterion in 32,882 steps. Comparing the two forward runs gives maximum
absolute complex changes of 0.00003277 in S11 and 0.00011631 in S21.

Combining both excitations from the identical ten-cell-padded model using
power-normalized **B = S A** gives a maximum singular value of **1.0000344** and
maximum reciprocity discrepancy |S12−S21| of **0.0001369**. The small excess above
one is reported without passivity enforcement. Independent column ratios would
give 1.03294, illustrating why they should not be mistaken for a normalized
multiport network. The incident-wave matrix condition number is at most 1.0682.

The full-matrix S11 complex RMSE against 655 overlapping published VNA samples
is **0.11634**. This is not a validated hardware model: local-mesh convergence,
loss and reference planes remain unresolved. The placement CSV lists R4 as
`R_0R_0201`, but the imported geometry has no link across those pads. The measured
population state is unknown. The fixture name refers to the shorter physical
stub; do not interpret it as proof of an electrically short-circuited termination.
No link was silently added to make the simulated curve agree with measurement.

Run against an archived copy of the original PML fixture geometry:

```console
python validation/run_boundary_case.py --source /runs/stub-short-pml --output /runs/padded10 --padding 10
python validation/run_boundary_case.py --source /runs/padded10 --output /runs/reverse10 --padding 0 --excitation 1
python validation/run_boundary_case.py --source /runs/stub-short-pml --output /runs/padded14 --padding 14
python validation/review_padding.py --forward /runs/padded10 --reverse /runs/reverse10 --larger /runs/padded14 --capped /runs/stub-short-pml --vna examples/stub_short/vna.csv --output /runs/review
python validation/plot_field.py --field /runs/padded10/ems/simulation/0/electric_xy.h5 --geometry /runs/padded10/ems/geometry/geometry.xml --output /runs/field-review
python -m unittest discover -s validation -p 'test_*.py' -v
```

The runner needs native openEMS/CSXCAD and the installed fork; the field plot
also needs h5py. The review refuses to combine columns with different geometry,
configuration, frequency samples or reference impedances. Raw complex waves,
native logs and geometry are preserved. Its E-field figure is a real 3 GHz
FDTD dump at z = −0.075 mm, normalized only for display. HDF5 Cartesian mesh
coordinates are already in metres; do not apply `mesh_scaling` a second time.
The field color is not calibrated absolute field strength or an EMC result.

The following section retains the earlier failed controls for traceability.

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
