"""Output-retention tests that run without openEMS, VTK or a PCB."""

import tempfile
import unittest
from pathlib import Path

from gerber2ems.workspace import prepare_outputs


class WorkspaceTests(unittest.TestCase):
    """Protect existing evidence and private paths from stage cleanup."""

    def setUp(self):
        """Create an isolated, disposable run root."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "ems"

    def tearDown(self):
        """Remove only the temporary fixture."""
        self.temp.cleanup()

    def test_rerun_preserves_existing_output_by_default(self):
        """A repeated command must stop without destroying evidence."""
        prepare_outputs(self.base, ["geometry", "simulation"])
        evidence = self.base / "simulation" / "raw.txt"
        evidence.write_text("previous run")
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["geometry", "simulation"])
        self.assertEqual(evidence.read_text(), "previous run")

    def test_overwrite_only_replaces_selected_stages(self):
        """An explicit geometry replacement must retain simulation results."""
        prepare_outputs(self.base, ["geometry", "simulation"])
        old_geometry = self.base / "geometry" / "old.xml"
        old_geometry.touch()
        preserved = self.base / "simulation" / "raw.txt"
        preserved.touch()
        prepare_outputs(self.base, ["geometry"], overwrite=True)
        self.assertFalse(old_geometry.exists())
        self.assertTrue(preserved.exists())

    def test_preflight_checks_every_path_before_replacing_any(self):
        """A late invalid path cannot erase an earlier stage."""
        prepare_outputs(self.base, ["geometry"])
        keep = self.base / "geometry" / "keep.xml"
        keep.touch()
        (self.base / "simulation").write_text("not a directory")
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["geometry", "simulation"], overwrite=True)
        self.assertTrue(keep.exists())

    def test_arbitrary_stage_and_nonempty_custom_output_are_rejected(self):
        """The overwrite flag is not permission to recursively delete arbitrary paths."""
        for stage in ("..", "../private", "geometry/../../private", str(self.root)):
            with self.assertRaises(ValueError):
                prepare_outputs(self.base, [stage], overwrite=True)
        custom = self.root / "plots"
        custom.mkdir()
        keep = custom / "prior.svg"
        keep.touch()
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["geometry"], overwrite=True, extra_output=custom)
        self.assertTrue(keep.exists())
        self.assertFalse(self.base.exists())

    def test_custom_output_inside_replaced_stage_is_rejected(self):
        """A destination must not be destroyed while preparing another destination."""
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["simulation"], True, self.base / "simulation" / "plots")

    def test_output_links_are_rejected(self):
        """A symlink to another project is never a cleanup destination."""
        outside = self.root / "private"
        outside.mkdir()
        keep = outside / "keep.txt"
        keep.touch()
        self.base.mkdir()
        link = self.base / "geometry"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["geometry"], overwrite=True)
        self.assertTrue(keep.exists())
        link.unlink()
        self.base.rmdir()
        self.base.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare_outputs(self.base, ["results"], overwrite=True)
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
