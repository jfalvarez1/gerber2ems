"""Prevent combining port excitations belonging to different physical models."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from review_padding import collect


class PortAssemblyTests(unittest.TestCase):
    """Supply distinct columns and deliberately inconsistent geometry/frequencies."""

    def test_only_matching_model_columns_are_combined(self):
        """Reject a model change even when the port arrays have matching shapes."""
        with tempfile.TemporaryDirectory() as directory:
            forward, reverse = (Path(directory) / name for name in ("forward", "reverse"))
            for root in (forward, reverse):
                (root / "ems/geometry").mkdir(parents=True)
                (root / "ems/geometry/geometry.xml").write_text("identical geometry")
                (root / "simulation.json").write_text("identical config")
            a = np.full((2, 2, 2), np.nan, complex)
            b = a.copy()
            a[:, 0, :] = [[1, 2], [3, 4]]
            b[:, 1, :] = [[5, 6], [7, 8]]
            np.savez(
                forward / "first-port-waves.npz",
                frequency_hz=[1e9, 2e9],
                reference_ohm=[50, 50],
                incident=a,
                reflected=a * 0.5,
            )
            reverse_file = reverse / "excitation-waves.npz"
            np.savez(reverse_file, frequency_hz=[1e9, 2e9], reference_ohm=[50, 50], incident=b, reflected=b * 0.25)
            result = collect(forward, reverse)
            np.testing.assert_array_equal(result["incident"][:, 0, :], a[:, 0, :])
            np.testing.assert_array_equal(result["incident"][:, 1, :], b[:, 1, :])
            np.testing.assert_array_equal(result["reflected"][:, 1, :], b[:, 1, :] * 0.25)
            (reverse / "ems/geometry/geometry.xml").write_text("different geometry")
            with self.assertRaisesRegex(ValueError, "different models"):
                collect(forward, reverse)
            (reverse / "ems/geometry/geometry.xml").write_text("identical geometry")
            np.savez(reverse_file, frequency_hz=[1e9, 3e9], reference_ohm=[50, 50], incident=b, reflected=b)
            with self.assertRaisesRegex(ValueError, "frequency_hz"):
                collect(forward, reverse)


if __name__ == "__main__":
    unittest.main()
