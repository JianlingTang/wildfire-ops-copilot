"use client";

import L from "leaflet";
import { useEffect, useMemo, useRef } from "react";

import { ApiHotspot, ApiHotspotVisualization, ApiOfficialWarningIncident } from "../../lib/api";

const australiaCenter: [number, number] = [-25.0, 134.0];

type LeafletContainer = HTMLDivElement & {
  _leaflet_id?: number;
};

export default function LeafletMap({
  center,
  hotspots,
  radiusKm = 30,
  warnings,
  riskLevel,
  visualization
}: {
  center?: [number, number];
  hotspots?: ApiHotspot[];
  radiusKm?: number;
  warnings?: (ApiOfficialWarningIncident & {lat: number; lon: number})[];
  riskLevel?: string | null;
  visualization?: ApiHotspotVisualization | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const hotspotLayerRef = useRef<L.LayerGroup | null>(null);
  const warningLayerRef = useRef<L.LayerGroup | null>(null);
  const visualizationLayerRef = useRef<L.LayerGroup | null>(null);
  const aoiCircleRef = useRef<L.Circle | null>(null);
  const canvasRendererRef = useRef<L.Canvas | null>(null);
  const renderTokenRef = useRef(0);
  const activeHotspots = useMemo(() => hotspots ?? [], [hotspots]);
  const activeWarnings = useMemo(() => warnings ?? [], [warnings]);

  useEffect(() => {
    const container = containerRef.current as LeafletContainer | null;
    if (!container || mapRef.current) {
      return;
    }

    if (container._leaflet_id) {
      delete container._leaflet_id;
    }

    const initialCenter = center ?? australiaCenter;
    const initialZoom = center ? 8 : 4;
    const map = L.map(container, {scrollWheelZoom: true}).setView(initialCenter, initialZoom);
    mapRef.current = map;

    let frameId = 0;
    let delayedInvalidateA = 0;
    let delayedInvalidateB = 0;

    const invalidate = () => {
      if (mapRef.current !== map) {
        return;
      }
      if (!container.isConnected || !map.getPane("mapPane")) {
        return;
      }
      map.invalidateSize(false);
    };

    const scheduleInvalidate = () => {
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(delayedInvalidateA);
      window.clearTimeout(delayedInvalidateB);

      frameId = window.requestAnimationFrame(() => {
        invalidate();
      });
      delayedInvalidateA = window.setTimeout(invalidate, 120);
      delayedInvalidateB = window.setTimeout(invalidate, 320);
    };

    const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
    canvasRendererRef.current = L.canvas({padding: 0.5});

    aoiCircleRef.current = L.circle(initialCenter, {
      color: colorForRisk(riskLevel),
      fillColor: colorForRisk(riskLevel),
      fillOpacity: 0.08,
      radius: radiusKm * 1000
    }).addTo(map);
    hotspotLayerRef.current = L.layerGroup().addTo(map);
    warningLayerRef.current = L.layerGroup().addTo(map);
    visualizationLayerRef.current = L.layerGroup().addTo(map);

    const resizeObserver = new ResizeObserver(() => {
      scheduleInvalidate();
    });
    resizeObserver.observe(container);

    map.whenReady(() => {
      scheduleInvalidate();
    });
    tileLayer.on("load", scheduleInvalidate);
    window.addEventListener("resize", scheduleInvalidate);

    if (document.fonts?.ready) {
      void document.fonts.ready.then(() => {
        scheduleInvalidate();
      });
    }

    scheduleInvalidate();

    return () => {
      resizeObserver.disconnect();
      tileLayer.off("load", scheduleInvalidate);
      window.removeEventListener("resize", scheduleInvalidate);
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(delayedInvalidateA);
      window.clearTimeout(delayedInvalidateB);
      map.remove();
      mapRef.current = null;
      delete container._leaflet_id;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const hotspotLayer = hotspotLayerRef.current;
    const warningLayer = warningLayerRef.current;
    const visualizationLayer = visualizationLayerRef.current;
    const aoiCircle = aoiCircleRef.current;
    const canvasRenderer = canvasRendererRef.current;
    if (!map || !hotspotLayer || !warningLayer || !visualizationLayer || !aoiCircle || !canvasRenderer) {
      return;
    }
    renderTokenRef.current += 1;
    const renderToken = renderTokenRef.current;

    const zoneColor = colorForRisk(riskLevel);
    aoiCircle.setStyle({color: zoneColor, fillColor: zoneColor});
    if (center) {
      aoiCircle.setLatLng(center);
      aoiCircle.setRadius(radiusKm * 1000);
      if (!map.hasLayer(aoiCircle)) {
        aoiCircle.addTo(map);
      }
    } else if (map.hasLayer(aoiCircle)) {
      aoiCircle.remove();
    }

    hotspotLayer.clearLayers();
    warningLayer.clearLayers();
    visualizationLayer.clearLayers();

    if (visualization) {
      visualization.contours.features.forEach((feature) => {
        const coordinates = feature.geometry.coordinates[0] ?? [];
        const latLngs = coordinates.map(([lon, lat]) => L.latLng(lat, lon));
        L.polygon(latLngs, {
          color: feature.properties.color,
          fillColor: feature.properties.color,
          fillOpacity: feature.properties.band === "Priority 1" ? 0.12 : 0.06,
          weight: feature.properties.band === "Priority 1" ? 3 : 2,
        })
          .bindPopup(`${feature.properties.band} · ${feature.properties.radius_km} km`)
          .addTo(visualizationLayer);
      });
      visualization.heatmap.cells.slice(0, 60).forEach((cell) => {
        L.circle([cell.lat, cell.lon], {
          color: "#b45309",
          fillColor: "#f97316",
          fillOpacity: Math.min(0.34, 0.08 + cell.normalized_intensity * 0.26),
          radius: Math.max(1200, 3600 * cell.normalized_intensity),
          renderer: canvasRenderer,
          weight: 0
        }).addTo(visualizationLayer);
      });
    }

    activeWarnings.forEach((warning) => {
      const position = L.latLng(warning.lat, warning.lon);
      L.circleMarker(position, {
        color: colorForWarning(warning.alert_level),
        fillColor: colorForWarning(warning.alert_level),
        fillOpacity: 0.18,
        radius: 10,
        renderer: canvasRenderer,
        weight: 4
      })
        .bindPopup(buildWarningPopup(warning))
        .addTo(warningLayer);
    });

    if (map.getPane("mapPane")) {
      if (center) {
        const centerBounds = L.latLng(center[0], center[1]).toBounds(radiusKm * 2000);
        map.fitBounds(centerBounds.pad(0.08), {maxZoom: 11});
      } else {
        map.setView(australiaCenter, 4);
      }
      map.invalidateSize(false);
    }

    const batchSize = center ? 400 : 300;
    let index = 0;

    const renderBatch = () => {
      if (renderTokenRef.current !== renderToken) {
        return;
      }

      const slice = activeHotspots.slice(index, index + batchSize);
      for (const hotspot of slice) {
        const position = L.latLng(hotspot.lat, hotspot.lon);
        L.circleMarker(position, {
          color: "#b72f2f",
          fillColor: "#d98b22",
          fillOpacity: 0.85,
          radius: center ? 7 : 4,
          renderer: canvasRenderer,
          weight: center ? 3 : 1.5
        })
          .bindPopup(buildHotspotPopup(hotspot))
          .addTo(hotspotLayer);
      }

      index += batchSize;
      if (index < activeHotspots.length) {
        window.requestAnimationFrame(renderBatch);
      }
    };

    renderBatch();
  }, [activeHotspots, activeWarnings, center, radiusKm, riskLevel, visualization]);

  return <div ref={containerRef} className="leafletMap h-full w-full" aria-label="Australian wildfire map" />;
}

function buildHotspotPopup(hotspot: ApiHotspot) {
  const state = hotspot.state ? `State: ${hotspot.state}` : null;
  const confidence = hotspot.confidence ? `Confidence: ${hotspot.confidence}` : "Confidence unavailable";
  const power = typeof hotspot.power === "number" ? `Power: ${hotspot.power}` : null;
  return [escapeText("Recent hotspot"), state, confidence, power, `Detected: ${hotspot.detected_at}`]
    .filter(Boolean)
    .join("<br />");
}

function buildWarningPopup(warning: ApiOfficialWarningIncident & {lat: number; lon: number}) {
  return [
    escapeText(warning.title),
    `Alert: ${warning.alert_level}`,
    `Status: ${warning.status}`,
    `Location: ${warning.location}`,
    `Distance: ${warning.distance_km} km`,
    warning.updated_at ? `Updated: ${warning.updated_at}` : null
  ]
    .filter(Boolean)
    .join("<br />");
}

function colorForRisk(riskLevel?: string | null) {
  if (riskLevel === "EXTREME") return "#991b1b";
  if (riskLevel === "HIGH") return "#b91c1c";
  if (riskLevel === "MODERATE") return "#c2410c";
  return "#0f766e";
}

function colorForWarning(alertLevel?: string) {
  if (alertLevel === "Emergency Warning") return "#991b1b";
  if (alertLevel === "Watch and Act") return "#c2410c";
  return "#d97706";
}

function escapeText(value: string) {
  return value.replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
