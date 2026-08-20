"""Render declared baseline-versus-alternative path comparisons."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

COLORS = ("#2563eb", "#0f766e", "#9333ea", "#b45309", "#be123c", "#4d7c0f")


def _write_empty_plot(path: Path) -> None:
    figure = Figure(figsize=(12, 7.2), dpi=100, facecolor="#f9fafb")
    canvas = FigureCanvasAgg(figure)
    figure.text(
        0.10,
        0.90,
        "Declared robustness checks",
        fontsize=20,
        weight="semibold",
        color="#111827",
    )
    figure.text(
        0.10,
        0.80,
        "No alternative path completed successfully",
        fontsize=13,
        color="#6b7280",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.print_png(path)  # type: ignore[no-untyped-call]


def write_comparison_plot(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        _write_empty_plot(path)
        return
    mpl.rcParams["font.family"] = "DejaVu Sans"
    baseline = {
        int(cast(int, row["horizon"])): float(
            cast(float, row["baseline_estimate"])
        )
        for row in rows
    }
    alternatives: dict[str, dict[int, float]] = {}
    for row in rows:
        alternative_id = str(row["alternative_id"])
        alternatives.setdefault(alternative_id, {})[
            int(cast(int, row["horizon"]))
        ] = float(cast(float, row["alternative_estimate"]))
    figure = Figure(figsize=(12, 7.2), dpi=100, facecolor="#f9fafb")
    canvas = FigureCanvasAgg(figure)
    axis = figure.add_axes((0.10, 0.17, 0.84, 0.67), facecolor="#f9fafb")
    horizons = sorted(baseline)
    axis.plot(
        horizons,
        [baseline[horizon] for horizon in horizons],
        color="#111827",
        linewidth=2.6,
        label="Baseline",
    )
    for index, (alternative_id, values) in enumerate(sorted(alternatives.items())):
        current = sorted(values)
        axis.plot(
            current,
            [values[horizon] for horizon in current],
            color=COLORS[index % len(COLORS)],
            linewidth=1.3,
            alpha=0.72,
            label=alternative_id[-6:],
        )
    axis.axhline(0.0, color="#6b7280", linewidth=1.0, linestyle=(0, (4, 4)))
    axis.set_xlabel("Horizon (quarters)", color="#374151", labelpad=12)
    axis.set_ylabel("Estimate", color="#374151", labelpad=12)
    axis.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    axis.tick_params(colors="#4b5563")
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d1d5db")
    axis.legend(
        loc="upper left",
        frameon=False,
        ncols=4,
        fontsize=8,
    )
    figure.text(
        0.10,
        0.92,
        "Declared robustness checks",
        fontsize=20,
        weight="semibold",
        color="#111827",
    )
    figure.text(
        0.10,
        0.875,
        "Baseline and every successfully executed alternative",
        fontsize=11,
        color="#6b7280",
    )
    figure.text(
        0.10,
        0.055,
        "Alternative paths are predeclared; no result-driven selection",
        fontsize=9,
        color="#9ca3af",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.print_png(path)  # type: ignore[no-untyped-call]
