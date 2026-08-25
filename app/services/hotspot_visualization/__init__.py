"""Hotspot heatmap/contour/interpretation visualization artifact builder.

Package layout:
- assembly.py: build_hotspot_visualization (orchestrator) and the AOI/heatmap
  geometry assembly (heatmap cells, radius filtering, dominant cluster).
- contour.py: matplotlib contour-band GeoJSON generation.
- density.py: KDE density grid math.
- render.py: matplotlib PNG preview rendering.
- interpretation.py: the plain-text AI interpretation summary.
"""

from __future__ import annotations

from app.services.hotspot_visualization.assembly import build_hotspot_visualization

__all__ = ["build_hotspot_visualization"]
