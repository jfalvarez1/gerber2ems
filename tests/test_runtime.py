"""Boundary regressions; skipped when the native simulation stack is absent."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HAS_NATIVE = all(importlib.util.find_spec(name) for name in ("openEMS", "CSXCAD", "nanomesh"))


@unittest.skipUnless(HAS_NATIVE, "Native simulation environment required")
class RuntimeTests(unittest.TestCase):
    """Exercise failures at external-tool boundaries without a full FDTD run."""

    def test_solver_failure_restores_working_directory(self):
        """A failed native call must not redirect subsequent file operations."""
        from gerber2ems import simulation

        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            def fail(*args, **kwargs):
                os.chdir(temporary)
                raise RuntimeError("Synthetic native failure")

            sim = simulation.Simulation.__new__(simulation.Simulation)
            sim.fdtd = SimpleNamespace(SetOverSampling=lambda value: None, Run=fail)
            config = SimpleNamespace(arguments=SimpleNamespace(oversampling=4, threads=2))
            try:
                with patch.object(simulation, "cfg", config), patch.object(simulation, "LogFilter", nullcontext):
                    with self.assertRaisesRegex(RuntimeError, "Synthetic native failure"):
                        sim.run(0)
                self.assertEqual(Path.cwd(), original)
            finally:
                os.chdir(original)

    def test_failed_rasterizer_never_reads_stale_png(self):
        """The actual importer must propagate the gerbv failure before opening an image."""
        from gerber2ems import importer

        failure = subprocess.CalledProcessError(1, ["gerbv"])
        config = SimpleNamespace(pixel_size=2.5)
        with patch.object(importer, "cfg", config), \
                patch.object(importer.subprocess, "run", side_effect=failure) as run, \
                patch.object(importer.PIL.Image, "open") as read:
            with self.assertRaises(subprocess.CalledProcessError):
                importer.gbr_to_png(Path("edge.gbr"), Path("board-F_Cu.gbr"))
            self.assertTrue(run.call_args.kwargs["check"])
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
