"""Structural ERC (Electrical Rule Check) over a raw SPICE netlist.

NOT full KiCad symbol/pin-level ERC (that needs a real .kicad_sch project —
out of scope for this synthetic golden dataset, see AGENTS.md). This checks
what a plain netlist can tell us: a ground reference exists, at least one
source drives the circuit, and no net is only ever mentioned once (a floating
node — usually a typo).
"""

import re

ELEMENT_LINE = re.compile(r"^([A-Za-z])\S*\s+(.+)$")


def _element_lines(netlist_text: str) -> list[tuple[str, list[str]]]:
    elements = []
    for line in netlist_text.splitlines():
        line = line.strip()
        if not line or line.startswith(("*", ".")):
            continue
        match = ELEMENT_LINE.match(line)
        if not match:
            continue
        kind, rest = match.groups()
        tokens = rest.split()
        elements.append((kind.upper(), tokens))
    return elements


def run_erc(netlist_text: str) -> list[str]:
    """Returns a list of violations — empty means the netlist passes."""
    violations = []
    elements = _element_lines(netlist_text)

    if not any("0" in tokens[:2] for _, tokens in elements):
        violations.append("no ground reference (node '0') found")

    if not any(kind in ("V", "I") for kind, _ in elements):
        violations.append("no independent source (V*/I*) found — circuit has no drive")

    net_occurrences: dict[str, int] = {}
    for _, tokens in elements:
        for node in tokens[:2]:
            net_occurrences[node] = net_occurrences.get(node, 0) + 1

    floating = [net for net, count in net_occurrences.items() if net != "0" and count < 2]
    if floating:
        violations.append(f"floating net(s) with a single connection: {', '.join(sorted(floating))}")

    return violations
