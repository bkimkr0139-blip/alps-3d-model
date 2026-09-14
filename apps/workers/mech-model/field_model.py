"""3D finite-difference electrostatic field solver for the AirInput
proximity-sensor twin — the §IF-02 "high-fidelity" tier of the 지시서's
two-tier architecture (§6.2).

Relationship to the P1 slice: fs_model.predict_proximity_capacitance stays
untouched as the legacy analytic preview. Every ΔC number produced HERE comes
from an actual discretized Laplace solve (∇·(ε∇φ)=0) over idealized
electrode/housing/cover/finger geometry — not from invented shape constants.

Honesty labels (지시서 §6.4 / HANDOFF §7 규칙 — synthetic 상수는 반드시 공개):
- Geometry is IDEALIZED but replicates the CAD model's real proportions
  (generate_airinput_step.py: 34×28 housing, 30×24 PCB, electrode center at
  (5, 0), Z_TOP=6.5). The material constants below are DISCLOSED
  ILLUSTRATIVE values, not measured Alps Alpine datasheet values.
- 접지 (ground) is modeled as real Dirichlet-0V structure: the housing
  shell, the ASIC QFN paddle, and an optional nearby ground plate
  (§11.2 GOLD "금속/접지 영향" scenario).
- Absolute accuracy against a commercial FEM/BEM solver is NOT validated.
  What pytest validates: an analytic parallel-plate sanity case, physical
  monotonicity, and bit-exact determinism. Correlation numbers computed
  from this module are pipeline checks, never accuracy claims (지시서 §13:
  감지 정확도를 완료로 주장하지 않는다).

Numerics / disclosed simplifications:
- Uniform cell-centered grid (h mm), 7-point stencil, red-black SOR
  (vectorized numpy — the only heavy dependency, already in this venv).
- Outer boundary: Neumann (∂φ/∂n = 0, open-space truncation) implemented by
  edge-replication padding in the update — the air box is deliberately
  large (≥7 mm beyond the housing on every side).
- The finger is body-GROUNDED (Dirichlet 0 V). A floating finger would need
  a second (charge-conservation) solve; the grounded bound is the
  conservative overestimate of coupling and is disclosed as such.
- Variant B's CAD split-ring notch (an anti-shorted-turn measure, i.e. an
  inductive concern) is electrostatically irrelevant and omitted. The ring
  IS reported as two half-ring analysis channels split at y=0 (E1/E2) by
  restricting the same charge integral to each half's cells — an analysis
  decomposition, not a CAD change, disclosed wherever it is reported.
- Layout B curve values (the ``delta_c_fF_at_d`` contract used by the
  existing correlation flow) sum the two channel ΔCs — the total ring
  response — while per-channel values travel in the run's artifact.

Sign convention (deliberate, matches P1's chain): the reported ΔC is the
SELF-capacitance change of the sensing electrode toward ground,
ΔC = C_self(finger) − C_self(no finger) > 0 — a grounded finger ADDS
self-capacitance, so closer ⇒ larger ΔC, continuous with P1's
``raw_count = offset + gain·ΔC``. (Mutual TX→RX coupling would DECREASE
with approach — the wrong sign for this chain — and is deliberately not
the channel definition.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --- Disclosed illustrative material constants (NOT measured values) --------
EPS_R_AIR = 1.0
EPS_R_PCB = 4.4  # FR-4 book value — "illustrative" in this context
EPS_R_GLOVE = 1.3  # porous knit effective ε (textile is ~90% air; a solid ε2.5
# slab would over-credit the glove's dielectric boost and invert the
# "glove degrades sensitivity" physics — disclosed illustrative value)
GLOVE_SHELL_MM = 1.2  # glove thickness (fs_model's analytic stand-in used a flat 1.5 mm standoff)

# Vacuum permittivity in fF/mm so capacitance comes out directly in fF
# (ε0 = 8.8541878128e-12 F/m = 8.8541878128e-3 fF/mm).
EPS0_FF_PER_MM = 8.8541878128e-3

V_TX = 1.0  # electrode drive potential (arbitrary — the problem is linear)

# --- Sensor stack dimensions (mm) — replicate generate_airinput_step.py -----
# Coordinates: Z-up, origin at the housing footprint center on its floor.
HOUSE_HALF_X_MM = 17.0
HOUSE_HALF_Y_MM = 14.0
HOUSE_WALL_MM = 1.5
HOUSE_FLOOR_MM = 1.2
HOUSE_TOP_MM = 6.5  # Z_TOP in the CAD script
PCB_HALF_X_MM = 15.0
PCB_HALF_Y_MM = 12.0
PCB_THICKNESS_MM = 1.6  # z: 1.2 → 2.8
ELECTRODE_CENTER_X_MM = 5.0
ELECTRODE_CENTER_Y_MM = 0.0
ELECTRODE_Z0_MM = 2.8  # PCB top
ELECTRODE_THICKNESS_MM = 0.08  # copper foil
COVER_HALF_X_MM = 15.3
COVER_HALF_Y_MM = 13.8
LAYOUT_B_OUTER_R_MM = 8.5  # must match generate_airinput_step.py
ASIC_PADDLE_CENTER = (-9.0, 4.0)  # QFN paddle (grounded shield mass)
ASIC_PADDLE_HALF = 2.5

FINGER_RADIUS_MM = 5.0  # bare fingertip pad radius
FINGER_HEIGHT_MM = 25.0  # finger column above its tip
DOMAIN_HALF_X_MM = 24.0
DOMAIN_HALF_Y_MM = 20.0
DOMAIN_TOP_MM = 32.5

LAYOUTS = ("A", "B")


@dataclass(frozen=True)
class GeometrySpec:
    """Idealized sensor stack — built from the seeded variant parameters."""

    electrode_area_mm2: float
    cover_thickness_mm: float
    cover_eps_r: float
    split_ring: bool  # False = layout A (solid center pad), True = layout B
    ground_plate: tuple[float, float, float, float, float] | None = None
    # ground_plate = (center_x, center_y, center_z, half_x, half_y) of a
    # grounded metal plate beside/above the sensor — the §11.2 "금속/접지
    # 영향" scenario structure.

    @property
    def layout(self) -> str:
        return "B" if self.split_ring else "A"


@dataclass(frozen=True)
class FingerState:
    """Fingertip pose over the touch surface (housing top, z = 6.5).

    ``x_mm``/``y_mm`` are lateral offsets of the finger axis from the
    housing- footprint center; ``gap_mm`` is the air gap between the finger
    tip (or the glove's outer surface, when gloved) and the touch surface.
    The finger is always normal to the surface — oblique poses are a
    documented PoC limitation.
    """

    x_mm: float
    y_mm: float
    gap_mm: float
    is_glove: bool = False


@dataclass
class FieldSolution:
    """Result of one Laplace solve — provenance numbers travel with it."""

    channel_q_ff: dict[str, float]  # channel id → electrode charge (fF)
    sweeps: int
    last_delta_phi: float  # max |Δφ| over free cells at the last check
    grid_shape: tuple[int, int, int]
    cell_mm: float
    converged: bool
    potential_slice: dict | None = field(default=None)


CHANNELS_BY_LAYOUT = {"A": ["E1"], "B": ["E1", "E2"]}  # B: half-ring split at y=0


def _band_layers(zs: np.ndarray, h: float, lo: float, hi: float) -> np.ndarray:
    """Boolean over the z axis: cell k spans [k·h, (k+1)·h]; True when the
    cell intersects [lo, hi).

    Intersection-based snapping (not center-in-band) so THIN structures —
    the 0.08 mm copper layer, a 1 mm cover at coarse h — can never fall
    between two cell centers and silently vanish from the mesh. Staircase
    error is ≤ one cell and is a disclosed discretization effect.
    """
    kk = np.arange(zs.size)
    cell_lo = kk * h
    cell_hi = cell_lo + h
    sel = (cell_hi > lo) & (cell_lo < hi)
    if not sel.any():
        # Degenerate placement (band exactly on a cell edge): snap to the
        # nearest layer rather than letting the structure vanish.
        sel[int(np.argmin(np.abs(zs - 0.5 * (lo + hi))))] = True
    return sel


def _electrode_cells(
    geom: GeometrySpec,
    X: np.ndarray,
    Y: np.ndarray,
    zs: np.ndarray,
    h: float,
) -> np.ndarray:
    """Boolean 3D mask of electrode cells (cell centers inside the pad)."""
    dx = X - ELECTRODE_CENTER_X_MM
    dy = Y - ELECTRODE_CENTER_Y_MM
    r2 = dx * dx + dy * dy
    zband = _band_layers(
        zs, h, ELECTRODE_Z0_MM, ELECTRODE_Z0_MM + ELECTRODE_THICKNESS_MM
    )
    if geom.split_ring:
        r_in2 = LAYOUT_B_OUTER_R_MM**2 - geom.electrode_area_mm2 / np.pi
        r_in = float(np.sqrt(max(r_in2, 0.0)))
        xy = (r2 <= LAYOUT_B_OUTER_R_MM**2) & (r2 >= r_in * r_in)
    else:
        r_pad = float(np.sqrt(geom.electrode_area_mm2 / np.pi))
        xy = r2 <= r_pad * r_pad
    return xy[:, :, None] & zband[None, None, :]


@dataclass
class StaticEnvironment:
    """Geometry-dependent-but-finger-independent parts of the grid."""

    geom: GeometrySpec
    h: float
    eps: np.ndarray  # relative permittivity per cell (finger/glove NOT applied)
    fixed: np.ndarray  # Dirichlet mask (housing/electrode/ASIC/plate)
    potential: np.ndarray  # Dirichlet values (1 V electrode, 0 V grounds)
    electrode_mask: np.ndarray
    channel_masks: dict[str, np.ndarray]
    shape: tuple[int, int, int]
    xs: np.ndarray
    ys: np.ndarray
    zs: np.ndarray


_ENV_CACHE: dict[tuple, StaticEnvironment] = {}


def build_environment(geom: GeometrySpec, h: float) -> StaticEnvironment:
    """Build (and cache) the finger-independent grid for one geometry.

    Cached by (geometry, h): a whole ΔC sweep reuses one environment, and a
    surrogate DOE reuses the baseline solve across all its poses.
    """
    key = (
        geom.electrode_area_mm2,
        round(geom.cover_thickness_mm, 4),
        round(geom.cover_eps_r, 4),
        geom.split_ring,
        geom.ground_plate,
        h,
    )
    cached = _ENV_CACHE.get(key)
    if cached is not None:
        return cached

    nx = int(round(2 * DOMAIN_HALF_X_MM / h))
    ny = int(round(2 * DOMAIN_HALF_Y_MM / h))
    nz = int(round(DOMAIN_TOP_MM / h))
    xs = (np.arange(nx) - (nx - 1) / 2.0) * h
    ys = (np.arange(ny) - (ny - 1) / 2.0) * h
    zs = (np.arange(nz) + 0.5) * h
    X, Y = np.meshgrid(xs, ys, indexing="ij")

    eps = np.full((nx, ny, nz), EPS_R_AIR, dtype=np.float64)
    fixed = np.zeros((nx, ny, nz), dtype=bool)
    potential = np.zeros((nx, ny, nz), dtype=np.float64)

    def slab(half_x: float, half_y: float) -> np.ndarray:
        return (
            (np.abs(X) <= half_x) & (np.abs(Y) <= half_y)
        )[:, :, None]

    def zband(lo: float, hi: float) -> np.ndarray:
        return _band_layers(zs, h, lo, hi)[None, None, :]

    # Cover slab (touch surface at z = HOUSE_TOP, cover hangs below it).
    cover_z = zband(HOUSE_TOP_MM - geom.cover_thickness_mm, HOUSE_TOP_MM)
    eps[slab(COVER_HALF_X_MM, COVER_HALF_Y_MM) & cover_z] = geom.cover_eps_r

    # PCB slab (z 1.2 → 2.8) across its footprint.
    eps[slab(PCB_HALF_X_MM, PCB_HALF_Y_MM) & zband(HOUSE_FLOOR_MM, ELECTRODE_Z0_MM)] = EPS_R_PCB

    # Grounded housing: floor + wall ring, from z=0 up to the top rim.
    housing = (
        (
            slab(HOUSE_HALF_X_MM, HOUSE_HALF_Y_MM)
            & ~slab(HOUSE_HALF_X_MM - HOUSE_WALL_MM, HOUSE_HALF_Y_MM - HOUSE_WALL_MM)
        )
        | (slab(HOUSE_HALF_X_MM, HOUSE_HALF_Y_MM) & zband(0.0, HOUSE_FLOOR_MM))
    ) & zband(0.0, HOUSE_TOP_MM)
    fixed |= housing  # potential stays 0 V

    # TX electrode on the PCB top (copper, Dirichlet V_TX).
    electrode = _electrode_cells(geom, X, Y, zs, h)
    fixed |= electrode
    potential[electrode] = V_TX

    # Grounded ASIC QFN paddle (same copper layer as the electrode).
    ax, ay = ASIC_PADDLE_CENTER
    asic = (
        ((np.abs(X - ax) <= ASIC_PADDLE_HALF) & (np.abs(Y - ay) <= ASIC_PADDLE_HALF))[
            :, :, None
        ]
        & _band_layers(
            zs, h, ELECTRODE_Z0_MM, ELECTRODE_Z0_MM + ELECTRODE_THICKNESS_MM
        )[None, None, :]
    )
    fixed |= asic

    # Optional external ground plate (금속/접지 영향 scenario) — a thin sheet
    # at z = gz: band so narrow the empty-guard snaps it to the nearest layer.
    if geom.ground_plate is not None:
        gx, gy, gz, ghx, ghy = geom.ground_plate
        plate = (
            ((np.abs(X - gx) <= ghx) & (np.abs(Y - gy) <= ghy))[:, :, None]
            & _band_layers(zs, h, gz, gz + 1e-9)[None, None, :]
        )
        fixed |= plate

    # Channel masks (charge-integration regions, all within the electrode):
    # layout A: one channel = the whole pad; layout B: half-ring split at
    # y = 0 (E1: y ≥ 0, E2: y < 0) — an analysis decomposition, disclosed.
    if geom.split_ring:
        # Full 3D electrode mask AND each half-space (broadcast over z).
        above = electrode & (Y >= 0)[:, :, None]
        below = electrode & (Y < 0)[:, :, None]
        channel_masks = {"E1": above, "E2": below}
    else:
        channel_masks = {"E1": electrode}

    env = StaticEnvironment(
        geom=geom,
        h=h,
        eps=eps,
        fixed=fixed,
        potential=potential,
        electrode_mask=electrode,
        channel_masks=channel_masks,
        shape=(nx, ny, nz),
        xs=xs,
        ys=ys,
        zs=zs,
    )
    _ENV_CACHE[key] = env
    return env


def _finger_masks(env: StaticEnvironment, finger: FingerState) -> tuple[np.ndarray, np.ndarray | None]:
    """(conductor mask, glove-shell mask) for one pose.

    Z bands use cell-INTERSECTION snapping: a center-based band would start
    the grounded finger on the first cell CENTER above the tip — up to one
    full cell of phantom air gap (1.25 mm at h=1.5) — and let the glove's
    shell hang below the core, inverting the glove-vs-bare physics.
    """
    X, Y = env.xs[:, None], env.ys[None, :]
    zs = env.zs
    z_surf = HOUSE_TOP_MM
    z_tip = z_surf + max(finger.gap_mm, 0.0)
    r2 = (X - finger.x_mm) ** 2 + (Y - finger.y_mm) ** 2
    core_xy = r2 <= FINGER_RADIUS_MM**2
    zband = _band_layers(zs, env.h, z_tip, z_tip + FINGER_HEIGHT_MM)[None, None, :]
    core = core_xy[:, :, None] & zband
    shell = None
    if finger.is_glove:
        outer_xy = r2 <= (FINGER_RADIUS_MM + GLOVE_SHELL_MM) ** 2
        zband_g = _band_layers(
            zs, env.h, z_tip - GLOVE_SHELL_MM, z_tip + FINGER_HEIGHT_MM + GLOVE_SHELL_MM
        )[None, None, :]
        shell = (outer_xy[:, :, None] & zband_g) & ~core
    return core, shell


def solve_potential(
    env: StaticEnvironment,
    finger: FingerState | None,
    max_sweeps: int = 2500,
    tol: float = 1e-5,
    want_potential_slice: bool = False,
    slice_stride: int = 0,
) -> FieldSolution:
    """One red-black SOR solve for one finger pose over a cached environment.

    Returns per-channel electrode charge (fF) + solver provenance.
    ``slice_stride`` overrides the y=0 slice downsampling (0 = auto, which
    keeps ~48 columns); the pose-slice library uses 2 so ~18 solved poses
    still fit a compact artifact.
    """
    eps = env.eps.copy()
    fixed = env.fixed
    potential = env.potential.copy()

    if finger is not None:
        core, shell = _finger_masks(env, finger)
        # Dirichlet wins over every material assignment.
        fixed = fixed | core
        potential[core] = 0.0
        if shell is not None:
            # Glove replaces whatever dielectric/air it wraps (never the
            # fixed conductor cells — those win by construction above).
            eps[shell] = EPS_R_GLOVE

    h = env.h

    def face_eps(cell: np.ndarray, nb: np.ndarray) -> np.ndarray:
        return 2.0 * cell * nb / (cell + nb)

    # Neighbor face conductances with edge-replicated ε (Neumann mirror at
    # the domain boundary: a boundary cell's exterior face mirrors itself).
    eps_p = np.pad(eps, 1, mode="edge")
    w_xp = face_eps(eps, eps_p[2:, 1:-1, 1:-1]) / (h * h)
    w_xm = face_eps(eps, eps_p[:-2, 1:-1, 1:-1]) / (h * h)
    w_yp = face_eps(eps, eps_p[1:-1, 2:, 1:-1]) / (h * h)
    w_ym = face_eps(eps, eps_p[1:-1, :-2, 1:-1]) / (h * h)
    w_zp = face_eps(eps, eps_p[1:-1, 1:-1, 2:]) / (h * h)
    w_zm = face_eps(eps, eps_p[1:-1, 1:-1, :-2]) / (h * h)
    w_sum = w_xp + w_xm + w_yp + w_ym + w_zp + w_zm

    free = ~fixed
    ii, jj, kk = np.indices(free.shape)
    ii_r, jj_r, kk_r = ii.ravel(), jj.ravel(), kk.ravel()
    parity = (ii + jj + kk) % 2
    red_idx = np.flatnonzero(free & (parity == 0))
    black_idx = np.flatnonzero(free & (parity == 1))

    omega = 1.75

    def sweep(indices: np.ndarray) -> None:
        if indices.size == 0:
            return
        i, j, k = ii_r[indices], jj_r[indices], kk_r[indices]
        # Padded potential: cell (i,j,k) lives at (i+1,j+1,k+1); edge
        # replication realizes the Neumann (mirror) outer boundary.
        p = np.pad(potential, 1, mode="edge")
        num = (
            w_xp[i, j, k] * p[i + 2, j + 1, k + 1]
            + w_xm[i, j, k] * p[i, j + 1, k + 1]
            + w_yp[i, j, k] * p[i + 1, j + 2, k + 1]
            + w_ym[i, j, k] * p[i + 1, j, k + 1]
            + w_zp[i, j, k] * p[i + 1, j + 1, k + 2]
            + w_zm[i, j, k] * p[i + 1, j + 1, k]
        )
        gs = num / w_sum[i, j, k]
        # In-place SOR relaxation on the color's free cells — scene-graph
        # style per-element mutation is the point of an iterative solver.
        potential[i, j, k] += omega * (gs - potential[i, j, k])

    sweeps = 0
    last_delta = np.inf
    converged = False
    for sweeps in range(1, max_sweeps + 1):
        if sweeps == 1:
            before = potential[free].copy()
        sweep(red_idx)
        sweep(black_idx)
        if sweeps % 20 == 0:
            after = potential[free]
            last_delta = float(np.max(np.abs(after - before)))
            before = after.copy()
            if last_delta < tol:
                converged = True
                break

    # Charge integration per channel: Q = Σ ε0·ε_face·(φ_cell − φ_nb)/h·h²
    # over faces of channel cells toward non-channel cells (all exposed
    # faces — fringing IS the signal). ε_face = harmonic mean (conservative
    # FD flux across a dielectric interface).
    charges: dict[str, float] = {}
    for ch, mask in env.channel_masks.items():
        q = 0.0
        for axis in (0, 1, 2):
            # Both face orientations of every neighbor pair: (c,n) then (n,c)
            # — a face carries flux iff the channel-side cell is in the
            # channel and the other side is not.
            for sl_c, sl_n in (
                (np.s_[:-1], np.s_[1:]),
                (np.s_[1:], np.s_[:-1]),
            ):
                c_slices = [slice(None)] * 3
                n_slices = [slice(None)] * 3
                c_slices[axis] = sl_c
                n_slices[axis] = sl_n
                c_mask = mask[tuple(c_slices)]
                n_mask = mask[tuple(n_slices)]
                face = c_mask & ~n_mask
                if not face.any():
                    continue
                eps_c = eps[tuple(c_slices)]
                eps_n = eps[tuple(n_slices)]
                eps_face = 2.0 * eps_c * eps_n / (eps_c + eps_n)
                dphi = potential[tuple(c_slices)] - potential[tuple(n_slices)]
                q += float(np.sum(eps_face[face] * dphi[face])) * h
        charges[ch] = q * EPS0_FF_PER_MM

    slice_out = None
    if want_potential_slice:
        j_mid = env.shape[1] // 2
        sub = potential[:, j_mid, :]
        stride = slice_stride if slice_stride > 0 else max(1, int(max(sub.shape) / 48))
        s = sub[::stride, ::stride]
        slice_out = {
            "plane": "y_mid",
            "values": [[round(float(v), 5) for v in row] for row in s],
        }

    return FieldSolution(
        channel_q_ff=charges,
        sweeps=sweeps,
        last_delta_phi=last_delta,
        grid_shape=env.shape,
        cell_mm=h,
        converged=converged,
        potential_slice=slice_out,
    )


# --- ΔC channel API -----------------------------------------------------------


def delta_c_self_fF(
    geom: GeometrySpec,
    finger: FingerState,
    cell_mm: float = 1.0,
    baseline_cache: dict | None = None,
    want_potential_slice: bool = False,
    slice_stride: int = 0,
) -> tuple[dict[str, float], FieldSolution]:
    """Per-channel self-capacitance change (fF) for one finger pose.

    ΔC = Q(finger present) − Q(no finger) per channel; closer ⇒ larger.
    ``baseline_cache`` (optional dict) memoizes the no-finger solve per
    (geometry, h) so sweeps/DOEs pay the baseline once.

    Default cell_mm=1.0 is the production resolution: a grid study
    (h=1.5/1.0/0.75) shows ΔC within ~±10% of the h=0.75 value at h=1.0
    at ~3 s/solve; h=0.75 costs ~10 s/solve and exceeds 800 SOR sweeps.
    The cell size travels with every artifact as solver provenance.
    """
    env = build_environment(geom, cell_mm)
    key = (
        geom.electrode_area_mm2,
        round(geom.cover_thickness_mm, 4),
        round(geom.cover_eps_r, 4),
        geom.split_ring,
        geom.ground_plate,
        cell_mm,
    )
    if baseline_cache is not None and key in baseline_cache:
        base = baseline_cache[key]
    else:
        base = solve_potential(env, None).channel_q_ff
        if baseline_cache is not None:
            baseline_cache[key] = base
    sol = solve_potential(
        env, finger, want_potential_slice=want_potential_slice, slice_stride=slice_stride
    )
    return {ch: sol.channel_q_ff[ch] - base[ch] for ch in sol.channel_q_ff}, sol


def predict_field_curve(
    electrode_area_mm2: float = 100.0,
    cover_thickness_mm: float = 1.0,
    cover_eps_r: float = 4.0,
    split_ring: bool = False,
    is_glove: bool = False,
    distance_min_mm: float = 0.0,
    distance_max_mm: float = 40.0,
    num_points: int = 13,
    cell_mm: float = 1.0,
    baseline_cache: dict | None = None,
    slices_out: list | None = None,
    slice_stride: int = 0,
) -> tuple[list[float], list[float]]:
    """ΔC(d) curve with the SAME contract shape as fs_model's analytic
    version: ascending distance (mm), ΔC monotone NON-INCREASING in d.
    (The analytic model's long power-law tail is strictly decreasing
    everywhere; the field solution's tail genuinely reaches ~0 at large
    gap, where solver noise makes strictly-decreasing unfalsifiable —
    near-range monotonicity is the pytest-pinned part.)
    d = air gap between finger tip (or glove surface) and the touch surface
    (housing top, z = 6.5) — the physical counterpart of the analytic
    model's ``d``. For the split ring (layout B) the curve value is the
    SUM of both half-ring channels — the total electrode response; the
    per-channel split travels in the run's artifact.

    ``slices_out`` (optional list) collects each solve's y=0 potential
    slice as it happens — the curve's poses ARE the slice library's gap
    axis, so the artifact gets a pose-resolved field view at zero extra
    solve cost. ``slice_stride`` downsamples those slices (0 = auto).
    """
    geom = GeometrySpec(electrode_area_mm2, cover_thickness_mm, cover_eps_r, split_ring)
    distances = np.linspace(distance_min_mm, distance_max_mm, num_points)
    out = []
    cache = baseline_cache if baseline_cache is not None else {}
    for d in distances:
        per_ch, sol = delta_c_self_fF(
            geom, FingerState(0.0, 0.0, float(d), is_glove), cell_mm, cache,
            want_potential_slice=slices_out is not None,
            slice_stride=slice_stride,
        )
        out.append(float(sum(per_ch.values())))
        if slices_out is not None and sol.potential_slice is not None:
            slices_out.append(
                {
                    "pose": {"x_mm": 0.0, "y_mm": 0.0, "gap_mm": round(float(d), 4), "is_glove": is_glove},
                    "slice": sol.potential_slice,
                }
            )
    return [float(d) for d in distances], out


def lateral_slice_sweep(
    geom: GeometrySpec,
    radii_mm: list[float],
    gap_mm: float = 0.0,
    is_glove: bool = False,
    cell_mm: float = 1.0,
    baseline_cache: dict | None = None,
    slice_stride: int = 2,
) -> list:
    """y=0 potential slices for OFF-CENTER finger poses, solved on a radial
    line (+x). Both shipped layouts are rotationally symmetric about the
    electrode axis (center pad / concentric rings), so the web client looks
    slices up by radius r = |(x, y)| — the library stores the SOLVED pose
    (x=r, y=0) and the client discloses that lookup as an approximation.
    r=0 is skipped: the gap sweep at center already covers it.
    """
    out = []
    cache = baseline_cache if baseline_cache is not None else {}
    for r in radii_mm:
        if r <= 0.0:
            continue
        _, sol = delta_c_self_fF(
            geom, FingerState(float(r), 0.0, gap_mm, is_glove), cell_mm, cache,
            want_potential_slice=True, slice_stride=slice_stride,
        )
        if sol.potential_slice is not None:
            out.append(
                {
                    "pose": {"x_mm": float(r), "y_mm": 0.0, "gap_mm": gap_mm, "is_glove": is_glove},
                    "slice": sol.potential_slice,
                }
            )
    return out
