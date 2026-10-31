"""Independent algebra and rejection checks for the evidence comparison script."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from compare_fixture import run_data


class ComparisonTests(unittest.TestCase):
    """Use a known reciprocal passive network with unequal port references."""

    def setUp(self):
        """Construct a passive reciprocal network with nontrivial incident waves."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "ems/simulation").mkdir(parents=True)
        self.frequency = np.array([1e9, 2e9, 3e9])
        self.z0 = np.array([50.0, 75.0])
        self.network = np.array([[0.1j, 0.7], [0.7, -0.1j]])
        self.incident = np.repeat(np.array([[[1.0, 0.2j], [0.1, 0.8]]]), 3, axis=0)
        self.reflected = self.network @ self.incident

    def write_run(self, partial=False, extra_log=""):
        """Persist voltage waves using the documented native archive axes."""
        incident = self.incident * np.sqrt(self.z0)[None, :, None]
        reflected = self.reflected * np.sqrt(self.z0)[None, :, None]
        if partial:
            incident[:, :, 1] = np.nan
            reflected[:, :, 1] = np.nan
        path = self.root / ("first-port-waves.npz" if partial else "ems/simulation/port-waves.npz")
        np.savez(
            path,
            frequency_hz=self.frequency,
            reference_ohm=self.z0,
            incident=np.moveaxis(incident, 0, 2),
            reflected=np.moveaxis(reflected, 0, 2),
        )
        (self.root / ("first-port.log" if partial else "run.log")).write_text(
            "Timestep: 100 || Energy: ~1.0e-10 (-20.00dB)\n"
            "Timestep: 200 || Energy: ~1.0e-14 (-60.00dB)\nTime for 200 iterations\n" + extra_log
        )

    def test_full_matrix_recovers_known_network_with_unequal_references(self):
        """Recover known power-wave S rather than the incorrect per-port ratio."""
        self.write_run()
        _, ratio, matrix, energy, metrics = run_data(self.root)
        np.testing.assert_allclose(matrix, np.broadcast_to(self.network, matrix.shape), atol=1e-14)
        self.assertGreater(np.max(abs(ratio - matrix)), 0.05)
        self.assertLess(metrics["maximum_singular_value_matrix"], 1)
        self.assertLess(metrics["maximum_reciprocity_error"], 1e-14)
        np.testing.assert_allclose(energy[:, 2], [-20, -60])

    def test_partial_run_never_claims_a_full_matrix(self):
        """Retain missing excitations and suppress full-network diagnostics."""
        self.write_run(partial=True)
        _, ratio, matrix, _, metrics = run_data(self.root)
        self.assertIsNone(matrix)
        self.assertFalse(metrics["full_matrix_available"])
        self.assertIsNone(metrics["maximum_singular_value_matrix"])
        self.assertTrue(np.isfinite(ratio[:, :, 0]).all())
        self.assertTrue(np.isnan(ratio[:, :, 1]).all())

    def test_cap_or_nonfinite_energy_prevents_stop_claim(self):
        """Reject both finite capped and divergent native runs."""
        for failure in ("Max. number of timesteps was reached", "Energy: ~ inf (- nandB)"):
            with self.subTest(failure=failure):
                self.write_run(extra_log=failure)
                self.assertFalse(run_data(self.root)[4]["time_domain_stop_reached"])

    def test_zero_reference_wave_rejected(self):
        """Reject a division by zero before drawing a misleading curve."""
        self.incident[:, 0, 0] = 0
        self.write_run()
        with self.assertRaisesRegex(ValueError, "zero incident"):
            run_data(self.root)

    def test_non_increasing_frequency_rejected(self):
        """Reject input that cannot be interpolated in frequency order."""
        self.frequency[1] = self.frequency[0]
        self.write_run()
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            run_data(self.root)


if __name__ == "__main__":
    unittest.main()
