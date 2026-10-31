"""Check a built wheel's runtime resources and SCM-generated version.

python tests/check_wheel.py path/to/gerber2ems-*.whl
"""
from email.parser import Parser
from pathlib import Path
import sys
from zipfile import ZipFile

for argument in sys.argv[1:]:
    with ZipFile(argument) as wheel:
        names = wheel.namelist()
        assert "gerber2ems/guidelines.yml" in names, "Runtime configuration is missing from the wheel"
        assert "gerber2ems/antmicro.mplstyle" in names, "Plot style is missing from the wheel"
        metadata = Parser().parsestr(wheel.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode())
        assert metadata["Version"] != "0.0.0", "SCM version generation is not enabled"
        print(f"PASS {Path(argument).name}: version {metadata['Version']}, guidelines and plot style included")
