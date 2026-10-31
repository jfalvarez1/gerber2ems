"""Geometry checks for boundary experiments without invoking the native solver."""

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from audit_domain import audit
from run_boundary_case import pad_geometry


class DomainTests(unittest.TestCase):
    """Use a known box so PML clearances have independent expected values."""

    def test_padding_preserves_geometry_and_all_original_coordinates(self):
        """Move the PML inward face outward without remeshing the physical board."""
        with tempfile.TemporaryDirectory() as directory:
            source, output = (Path(directory) / name for name in ("input.xml", "output.xml"))
            lines = ",".join(str(i) for i in range(-10, 11))
            source.write_text(
                '<ContinuousStructure><RectilinearGrid DeltaUnit="0.001">'
                + "".join(f'<{a}Lines Qty="21">{lines}</{a}Lines>' for a in "XYZ")
                + '</RectilinearGrid><Properties><Metal Name="board"><Primitives>'
                '<Box><P1 X="-3" Y="-1" Z="-1"/><P2 X="3" Y="1" Z="1"/></Box>'
                "</Primitives></Metal></Properties></ContinuousStructure>"
            )
            original = source.read_bytes()
            self.assertEqual(audit(source)["properties"][0]["overlaps_PML_axes"], ["x"])
            pad_geometry(source, output, 10)
            result = audit(output)
            self.assertEqual(result["mesh_lines"], [41, 41, 41])
            np.testing.assert_allclose(result["properties"][0]["clearance_to_PML_mm"], [9, 11, 11], rtol=1e-14)
            self.assertEqual(result["properties"][0]["overlaps_PML_axes"], [])
            for axis in "XYZ":
                values = np.fromstring(ET.parse(output).find(f"RectilinearGrid/{axis}Lines").text, sep=",")
                np.testing.assert_array_equal(values[10:-10], np.arange(-10, 11))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(
                ET.tostring(ET.parse(source).find("Properties")), ET.tostring(ET.parse(output).find("Properties"))
            )


if __name__ == "__main__":
    unittest.main()
