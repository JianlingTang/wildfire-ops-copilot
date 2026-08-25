import type { ApiRiskTrend } from "../../lib/api";
import { DownloadArtifactButton } from "./DownloadArtifactButton";
import { downloadDataUrl } from "./download";

export function coerceRiskTrend(value: unknown): ApiRiskTrend | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const trend = value as ApiRiskTrend;
  return Array.isArray(trend.points) ? trend : null;
}

export function RiskTrendChart({trend}: {trend: ApiRiskTrend}) {
  const points = trend.points.filter((point) => typeof point.risk_score === "number");
  if (!points.length) {
    return null;
  }
  const chart = buildRiskTrendChart(points);
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Risk Trend</div>
          <div className="mt-1 text-sm font-semibold text-slate-800">{trend.region_name}</div>
        </div>
        <DownloadArtifactButton label="Download risk trend figure" onClick={() => downloadRiskTrendPng(trend, chart)} />
      </div>
      <div className="px-3 py-3">
        <svg
          aria-label="Risk trend chart with Date x-axis and Risk Score y-axis"
          className="block h-auto w-full"
          role="img"
          viewBox={`0 0 ${chart.width} ${chart.height}`}
        >
          <rect fill="#ffffff" height={chart.height} width={chart.width} x="0" y="0" />
          {chart.yTicks.map((tick) => (
            <g key={tick.value}>
              <line stroke="#e2e8f0" strokeDasharray="5 8" x1={chart.plotLeft} x2={chart.plotRight} y1={tick.y} y2={tick.y} />
              <text fill="#64748b" fontSize="11" textAnchor="end" x={chart.plotLeft - 10} y={tick.y + 4}>
                {tick.value}
              </text>
            </g>
          ))}
          <line stroke="#94a3b8" strokeWidth="1.4" x1={chart.plotLeft} x2={chart.plotRight} y1={chart.plotBottom} y2={chart.plotBottom} />
          <line stroke="#94a3b8" strokeWidth="1.4" x1={chart.plotLeft} x2={chart.plotLeft} y1={chart.plotTop} y2={chart.plotBottom} />
          {chart.segments.map((segment) => (
            <line
              key={segment.key}
              stroke={segment.color}
              strokeDasharray={segment.dash}
              strokeLinecap="round"
              strokeWidth="3"
              x1={segment.x1}
              x2={segment.x2}
              y1={segment.y1}
              y2={segment.y2}
            />
          ))}
          {chart.points.map((point) => (
            <g key={`${point.date}-${point.type}`}>
              <circle cx={point.x} cy={point.y} fill="#ffffff" r={point.type === "current" ? 6 : 4.5} stroke={point.color} strokeWidth={point.type === "current" ? 3 : 2.4} />
            </g>
          ))}
          {chart.xLabels.map((label) => (
            <text fill="#64748b" fontSize="10" key={label.key} textAnchor="middle" transform={`rotate(-30 ${label.x} ${chart.plotBottom + 23})`} x={label.x} y={chart.plotBottom + 23}>
              {label.text}
            </text>
          ))}
          <text fill="#475569" fontSize="12" fontWeight="700" textAnchor="middle" x={(chart.plotLeft + chart.plotRight) / 2} y={chart.height - 10}>
            Date
          </text>
          <text fill="#475569" fontSize="12" fontWeight="700" textAnchor="middle" transform={`rotate(-90 15 ${(chart.plotTop + chart.plotBottom) / 2})`} x="15" y={(chart.plotTop + chart.plotBottom) / 2}>
            Risk Score
          </text>
        </svg>
      </div>
      <div className="flex flex-wrap gap-2 px-3 pb-3 text-[11px] text-slate-500">
        {points.map((point) => (
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1" key={`${point.date}-${point.type}`} style={{borderColor: riskColor(point.risk_level)}}>
            {point.date}: {point.risk_level} {point.risk_score}/100
          </span>
        ))}
      </div>
      <div className="border-t border-slate-100 px-3 py-2 text-xs leading-5 text-slate-500">{trend.note}</div>
    </div>
  );
}

function buildRiskTrendChart(points: ApiRiskTrend["points"]) {
  const width = 760;
  const height = 310;
  const plotLeft = 58;
  const plotRight = width - 22;
  const plotTop = 22;
  const plotBottom = height - 64;
  const plotWidth = plotRight - plotLeft;
  const plotHeight = plotBottom - plotTop;
  const scaledPoints = points.map((point, index) => {
    const x = points.length === 1 ? plotLeft + plotWidth / 2 : plotLeft + (index / (points.length - 1)) * plotWidth;
    const y = plotBottom - (Math.max(0, Math.min(100, point.risk_score)) / 100) * plotHeight;
    return {...point, x, y, color: riskColor(point.risk_level)};
  });
  const segments = scaledPoints.slice(1).map((point, index) => {
    const previous = scaledPoints[index];
    return {
      key: `${previous.date}-${point.date}`,
      x1: previous.x,
      y1: previous.y,
      x2: point.x,
      y2: point.y,
      color: point.color,
      dash: point.type === "forecast" ? "8 6" : point.type === "historical" ? "1 0" : "1 0"
    };
  });
  const yTicks = [0, 25, 50, 75, 100].map((value) => ({
    value,
    y: plotBottom - (value / 100) * plotHeight
  }));
  const xLabels = scaledPoints
    .filter((_, index) => index % 2 === 0 || index === scaledPoints.length - 1)
    .map((point) => ({
      key: `${point.date}-${point.type}`,
      text: shortDateLabel(point.date),
      x: point.x
    }));
  return {height, plotBottom, plotLeft, plotRight, plotTop, points: scaledPoints, segments, width, xLabels, yTicks};
}

function riskColor(level: string) {
  if (level === "EXTREME") return "#b91c1c";
  if (level === "HIGH") return "#b45309";
  if (level === "MODERATE") return "#ca8a04";
  return "#15803d";
}

function shortDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-AU", {day: "2-digit", month: "short"}).format(date);
}

function downloadRiskTrendPng(trend: ApiRiskTrend, chart: ReturnType<typeof buildRiskTrendChart>) {
  const svg = riskTrendSvgMarkup(chart);
  const image = new Image();
  const url = URL.createObjectURL(new Blob([svg], {type: "image/svg+xml;charset=utf-8"}));
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = chart.width * 2;
    canvas.height = chart.height * 2;
    const context = canvas.getContext("2d");
    if (!context) {
      URL.revokeObjectURL(url);
      return;
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    URL.revokeObjectURL(url);
    downloadDataUrl(canvas.toDataURL("image/png"), trend.downloads?.png_filename ?? "risk-trend.png");
  };
  image.onerror = () => URL.revokeObjectURL(url);
  image.src = url;
}

function riskTrendSvgMarkup(chart: ReturnType<typeof buildRiskTrendChart>) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${chart.width}" height="${chart.height}" viewBox="0 0 ${chart.width} ${chart.height}">
<rect fill="#ffffff" height="${chart.height}" width="${chart.width}" x="0" y="0" />
${chart.yTicks.map((tick) => `<g><line stroke="#e2e8f0" stroke-dasharray="5 8" x1="${chart.plotLeft}" x2="${chart.plotRight}" y1="${tick.y}" y2="${tick.y}" /><text fill="#64748b" font-size="11" text-anchor="end" x="${chart.plotLeft - 10}" y="${tick.y + 4}">${tick.value}</text></g>`).join("")}
<line stroke="#94a3b8" stroke-width="1.4" x1="${chart.plotLeft}" x2="${chart.plotRight}" y1="${chart.plotBottom}" y2="${chart.plotBottom}" />
<line stroke="#94a3b8" stroke-width="1.4" x1="${chart.plotLeft}" x2="${chart.plotLeft}" y1="${chart.plotTop}" y2="${chart.plotBottom}" />
${chart.segments.map((segment) => `<line stroke="${segment.color}" stroke-dasharray="${segment.dash}" stroke-linecap="round" stroke-width="3" x1="${segment.x1}" x2="${segment.x2}" y1="${segment.y1}" y2="${segment.y2}" />`).join("")}
${chart.points.map((point) => `<circle cx="${point.x}" cy="${point.y}" fill="#ffffff" r="${point.type === "current" ? 6 : 4.5}" stroke="${point.color}" stroke-width="${point.type === "current" ? 3 : 2.4}" />`).join("")}
${chart.xLabels.map((label) => `<text fill="#64748b" font-size="10" text-anchor="middle" transform="rotate(-30 ${label.x} ${chart.plotBottom + 23})" x="${label.x}" y="${chart.plotBottom + 23}">${escapeXml(label.text)}</text>`).join("")}
<text fill="#475569" font-size="12" font-weight="700" text-anchor="middle" x="${(chart.plotLeft + chart.plotRight) / 2}" y="${chart.height - 10}">Date</text>
<text fill="#475569" font-size="12" font-weight="700" text-anchor="middle" transform="rotate(-90 15 ${(chart.plotTop + chart.plotBottom) / 2})" x="15" y="${(chart.plotTop + chart.plotBottom) / 2}">Risk Score</text>
</svg>`;
}

function escapeXml(value: string) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}
