"""Render stable, high-integrity dynamic-path charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from time_series_dynamics.models import ClaimPolicy, DynamicsRequest, HorizonEstimate
from time_series_dynamics.time_axis import horizon_unit

COLORS = {
    "identified_shock_irf": "#2563eb",
    "conditional_dynamic_association": "#0f766e",
}
TITLES = {
    "identified_shock_irf": "Dynamic response to an identified shock",
    "conditional_dynamic_association": "Conditional dynamic association",
}


def write_dynamic_path(
    path: Path,
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
    policy: ClaimPolicy,
) -> None:
    mpl.rcParams["font.family"] = "DejaVu Sans"
    figure = Figure(figsize=(12, 7.2), dpi=100, facecolor="#f9fafb")
    canvas = FigureCanvasAgg(figure)
    axis = figure.add_axes((0.10, 0.17, 0.84, 0.67), facecolor="#f9fafb")
    horizons = np.asarray([item.horizon for item in estimates], dtype=float)
    values = np.asarray([item.estimate for item in estimates], dtype=float)
    lower = np.asarray([item.confidence_lower for item in estimates], dtype=float)
    upper = np.asarray([item.confidence_upper for item in estimates], dtype=float)
    color = COLORS[policy.analysis_track]

    axis.fill_between(horizons, lower, upper, color=color, alpha=0.14, linewidth=0)
    axis.plot(horizons, values, color=color, linewidth=2.2)
    axis.axhline(0.0, color="#6b7280", linewidth=1.0, linestyle=(0, (4, 4)))
    axis.set_xlabel(
        f"Horizon ({horizon_unit(request.frequency)})",
        color="#374151",
        labelpad=12,
    )
    axis.set_ylabel(request.output_unit, color="#374151", labelpad=12)
    axis.set_xticks(horizons[:: max(1, len(horizons) // 9)])
    axis.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    axis.tick_params(colors="#4b5563")
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d1d5db")

    figure.text(
        0.10,
        0.92,
        TITLES[policy.analysis_track],
        fontsize=20,
        weight="semibold",
        color="#111827",
    )
    figure.text(
        0.10,
        0.875,
        f"{int(request.confidence_level * 100)}% pointwise interval · "
        f"{request.sample_policy} · HAC({request.hac_maxlags})",
        fontsize=11,
        color="#6b7280",
    )
    figure.text(
        0.10,
        0.055,
        "Source: pinned research Artifact · Shaded area is pointwise uncertainty",
        fontsize=9,
        color="#9ca3af",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.print_png(path)  # type: ignore[no-untyped-call]
