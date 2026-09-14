"""Runs an ngspice contact-resistance sweep over a netlist and parses results.

The netlist artifact defines the fixed circuit (source + pull-up + the
`Rcontact` element); this module appends a `.control` block that sweeps
`Rcontact` and reads back V(OUT) at each point — the representative scenario
FR-05 allows ("한 개의 대표 시나리오만 End-to-End로 검증").
"""

import re
import subprocess
import tempfile
from pathlib import Path

NGSPICE_BIN = "ngspice"
PRINT_LINE = re.compile(r"v\(out\)\s*=\s*([-\d.eE+]+)")


def build_sweep_script(netlist_body: str, sweep_ohms: list[float]) -> str:
    body = netlist_body.strip()
    if body.endswith(".end"):
        body = body[: -len(".end")].strip()

    sweep_values = " ".join(str(v) for v in sweep_ohms)
    control_block = f"""
.control
set noaskquit
foreach rc {sweep_values}
  alter Rcontact = $rc
  op
  print v(out)
end
quit
.endc
.end
"""
    return f"{body}\n{control_block}"


def run_sweep(netlist_body: str, sweep_ohms: list[float], timeout_s: int = 30) -> tuple[list[float], str]:
    """Returns (V(OUT) per sweep point, raw ngspice stdout — kept as evidence)."""
    script = build_sweep_script(netlist_body, sweep_ohms)
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "sweep.cir"
        script_path.write_text(script)
        result = subprocess.run(
            [NGSPICE_BIN, "-b", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

    values = [float(m) for m in PRINT_LINE.findall(result.stdout)]
    if len(values) != len(sweep_ohms):
        raise RuntimeError(
            f"ngspice produced {len(values)} V(OUT) readings, expected {len(sweep_ohms)}.\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return values, result.stdout
