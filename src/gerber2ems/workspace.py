"""Output lifecycle, independent of the solver and its native dependencies.

Only named stage directories directly under the run's ems directory can be
replaced. External plot destinations must be empty. Preflight every destination
before touching any of them so an error cannot silently discard an earlier run.
"""

import shutil
from pathlib import Path
from typing import Iterable

STAGES = frozenset({"geometry", "simulation", "results"})


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def prepare_outputs(base: Path, stages: Iterable[str], overwrite: bool = False,
                    extra_output: Path | None = None) -> None:
    """Validate all destinations, then create or explicitly replace owned stages."""
    base = base.absolute()
    stages = tuple(stages)
    if any(stage not in STAGES for stage in stages):
        raise ValueError("Unknown simulation output stage")
    if _is_link(base) or (base.exists() and not base.is_dir()):
        raise ValueError(f"Output root must be a real directory: {base}")
    paths = [base / stage for stage in stages]
    for path in paths:
        if _is_link(path) or path.resolve().parent != base.resolve():
            raise ValueError(f"Refusing output link or path outside the run directory: {path}")
        if path.exists():
            if not path.is_dir():
                raise ValueError(f"Output path is not a directory: {path}")
            if any(path.iterdir()) and not overwrite:
                raise ValueError(f"Previous output exists: {path}. Use a fresh run folder or --overwrite.")
    if extra_output is not None:
        extra_output = extra_output.absolute()
        if _is_link(extra_output) or (extra_output.exists() and
                                     (not extra_output.is_dir() or any(extra_output.iterdir()))):
            raise ValueError(f"Custom plot output must be a new or empty directory: {extra_output}")
        # A custom directory must not disappear inside a stage selected for replacement.
        if any(extra_output.resolve().is_relative_to(path.resolve()) for path in paths):
            raise ValueError("Custom plot output overlaps a generated stage")
    base.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists() and overwrite:
            shutil.rmtree(path)
        path.mkdir(exist_ok=True)
    if extra_output is not None:
        extra_output.mkdir(parents=True, exist_ok=True)
