# Fork maintenance and run retention

This fork adds output safety and reproducibility checks around Antmicro's
existing simulation pipeline. It does not replace the upstream mesher or claim
that every extracted network is accurate.

## Re-running safely

Use a separate copied example/run directory for each configuration. By default,
a command refuses nonempty selected `ems/geometry`, `ems/simulation` or
`ems/results` directories. `--overwrite` explicitly replaces only the selected
stage directories. All destinations are checked before any cleanup. Output-root
and stage symlinks/junctions are rejected. A custom `--output` destination must
be new or empty even when `--overwrite` is supplied.

There is no automatic expiration, upload or background deletion of run data.
Keep the original configuration and fab inputs with each archived result.
`--vertical` and `--all` retain upstream behavior: preprocessing rewrites the
working `simulation.json` with resolved port information. Work on a **copy**;
the source configuration belongs in version control or a separate input archive.
The safeguards protect ordinary local runs, not an adversary concurrently
changing filesystem paths. This CLI is not an untrusted multi-user job service.

## Execution and diagnostics

`--threads N` limits openEMS workers (default 4; positive integer). The mesher
and numerical libraries may use separate workers. openEMS's changed working
directory is restored even if it raises an exception. Rasterizer failures keep
gerbv's stderr and fail immediately, instead of trying to read a missing/stale
PNG. No-excitation configurations fail before output preparation.

`ems/simulation/port-waves.npz` retains `frequency_hz`, complex voltage-wave
`incident` and `reflected` arrays, and `reference_ohm`. Array order is
`[measured port, excitation port, frequency]`. Unexcited columns contain NaN;
they are missing data, not zeros. Load with `numpy.load(..., allow_pickle=False)`.

S-parameter extraction still follows upstream's per-excitation wave ratios.
A partial excitation does not establish a full multiport matrix or passivity.
Record this limitation when using these CSVs, especially if the unexcited ports
have appreciable incident waves. Retained waves enable a later independent
extraction audit. Do not silently reinterpret them as calibrated measurements.

## Ownership and checks

- `workspace.py`: filesystem lifecycle; standard-library-only tests in
  `tests/test_workspace.py`.
- `main.py`: CLI orchestration and output planning.
- `importer.py`: Gerber rasterization/import.
- `simulation.py`: native solver boundary and execution.
- `postprocess.py`: numerical extraction, plots and CSV formatting.

Run `PYTHONPATH=src python -m unittest discover -s tests -v` on Linux. Windows
PowerShell: set `$env:PYTHONPATH='src'`, then run the same Python command. CI runs
these without native dependencies; it does **not** claim an FDTD validation run.
Two additional runtime boundary tests run when the native stack is installed:
solver failure restores the working directory, and gerbv failure stops before
opening an image. CI without that stack reports those tests as skipped.
For solver changes, also run a documented fixture with exact input hashes,
solver commits, environment versions, raw data and independent physical checks.

Prefer small typed functions with explicit inputs over extending singleton
configuration state. Avoid unrelated reformatting. Preserve upstream licensing
and separate synthetic tests from measured-reference comparisons. Large native
installations, private PCB files and field dumps do not belong in git.
