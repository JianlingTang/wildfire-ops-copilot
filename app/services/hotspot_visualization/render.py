"""Matplotlib PNG preview rendering for the hotspot visualization."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def _preview_image(
    region_name: str,
    radius_km: float,
    aoi_center: tuple[float, float],
    hotspot_center: tuple[float, float],
    cells: list[dict[str, Any]],
    density: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    width_px = 960
    height_px = 640
    figure = Figure(figsize=(width_px / 160, height_px / 160), dpi=160)
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(1, 1, 1)
    axes.set_facecolor("#f8fafc")
    figure.subplots_adjust(left=0.08, right=0.88, bottom=0.09, top=0.92)

    _plot_density(axes, figure, density)
    _plot_hotspot_cells(axes, cells)
    _plot_centers(axes, aoi_center, hotspot_center)
    _style_axes(axes, figure, region_name, radius_km, density["bounds"], width_px / height_px)

    buffer = BytesIO()
    canvas.print_png(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "format": "image/png",
        "encoding": "base64",
        "filename": filename,
        "data_url": f"data:image/png;base64,{encoded}",
        "width": width_px,
        "height": height_px,
        "alt": f"{region_name} matplotlib hotspot contour preview",
    }


def _plot_density(axes: Any, figure: Any, density: dict[str, Any]) -> None:
    if not density["levels"]:
        return
    contour_fill = axes.contourf(
        density["lons"], density["lats"], density["values"], levels=density["levels"], cmap="YlOrRd", alpha=0.82
    )
    axes.contour(
        density["lons"],
        density["lats"],
        density["values"],
        levels=density["line_levels"],
        colors=["#d97706", "#c2410c", "#991b1b"],
        linewidths=1.5,
    )
    colorbar = figure.colorbar(contour_fill, ax=axes, fraction=0.038, pad=0.02)
    colorbar.set_label("KDE density", fontsize=8, color="#334155")
    colorbar.ax.tick_params(labelsize=7, colors="#475569")


def _plot_hotspot_cells(axes: Any, cells: list[dict[str, Any]]) -> None:
    if not cells:
        return
    lats = [float(cell["lat"]) for cell in cells]
    lons = [float(cell["lon"]) for cell in cells]
    intensities = [float(cell.get("normalized_intensity") or 0) for cell in cells]
    sizes = [40 + intensity * 220 for intensity in intensities]
    axes.scatter(
        lons,
        lats,
        c=intensities,
        cmap="YlOrRd",
        edgecolors="#7f1d1d",
        linewidths=0.35,
        s=sizes,
        alpha=0.82,
        label="Hotspot density",
    )


def _plot_centers(axes: Any, aoi_center: tuple[float, float], hotspot_center: tuple[float, float]) -> None:
    axes.scatter(
        [hotspot_center[1]],
        [hotspot_center[0]],
        marker="+",
        s=150,
        color="#0f172a",
        linewidths=1.8,
        label="Hotspot center (+)",
    )
    if aoi_center != hotspot_center:
        axes.scatter(
            [aoi_center[1]],
            [aoi_center[0]],
            marker="x",
            s=54,
            color="#334155",
            linewidths=1.3,
            label="AOI center (x)",
        )


def _style_axes(
    axes: Any,
    figure: Any,
    region_name: str,
    radius_km: float,
    bounds: tuple[float, float, float, float],
    target_aspect: float,
) -> None:
    axes.set_title(f"{region_name} - {radius_km:g} km contour map", fontsize=10, color="#0f172a", pad=6)
    axes.set_xlabel("Longitude", fontsize=8, color="#475569")
    axes.set_ylabel("Latitude", fontsize=8, color="#475569")
    axes.tick_params(axis="both", labelsize=7, colors="#475569")
    axes.legend(loc="upper right", fontsize=7, framealpha=0.86)
    axes.set_aspect("equal", adjustable="box")
    _set_preview_bounds(axes, bounds, target_aspect)
    axes.margins(0)
    figure.tight_layout(pad=1.1)


def _set_preview_bounds(axes: Any, bounds: tuple[float, float, float, float], target_aspect: float) -> None:
    west, south, east, north = bounds
    width = max(east - west, 0.001)
    height = max(north - south, 0.001)
    current_aspect = width / height
    if current_aspect < target_aspect:
        extra = (height * target_aspect - width) / 2.0
        west -= extra
        east += extra
    elif current_aspect > target_aspect:
        extra = (width / target_aspect - height) / 2.0
        south -= extra
        north += extra
    axes.set_xlim(west, east)
    axes.set_ylim(south, north)
