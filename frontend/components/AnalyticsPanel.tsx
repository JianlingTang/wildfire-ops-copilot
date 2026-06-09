import { Activity } from "lucide-react";

import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

const trendPoints = [
  {label: "06:00", value: 42},
  {label: "07:00", value: 51},
  {label: "08:00", value: 63},
  {label: "09:00", value: 78},
  {label: "10:00", value: 83},
  {label: "11:00", value: 76}
];

const chartHeight = 120;
const chartWidth = 240;
const maxValue = 100;

const coordinates = trendPoints.map((point, index) => {
  const x = (index / (trendPoints.length - 1)) * chartWidth;
  const y = chartHeight - (point.value / maxValue) * chartHeight;
  return {x, y, ...point};
});

const linePath = coordinates.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
const areaPath = `${linePath} L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`;

export function AnalyticsPanel({className}: {className?: string}) {
  return (
    <Card id="analytics-panel" className={cn("flex h-full flex-col border-slate-200 shadow-sm", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4" />
            Wildfire Risk Trend
          </CardTitle>
          <Badge variant="outline">Risk trend</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="space-y-2">
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <svg
            aria-label="Wildfire risk pressure trend"
            className="h-32 w-full"
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            preserveAspectRatio="none"
            role="img"
          >
            <defs>
              <linearGradient id="riskTrendFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#c2410c" stopOpacity="0.24" />
                <stop offset="100%" stopColor="#c2410c" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            <line x1="0" x2={chartWidth} y1={24} y2={24} stroke="#f1f5f9" strokeDasharray="4 4" />
            <line x1="0" x2={chartWidth} y1={60} y2={60} stroke="#e2e8f0" strokeDasharray="4 4" />
            <line x1="0" x2={chartWidth} y1={96} y2={96} stroke="#f1f5f9" strokeDasharray="4 4" />
            <path d={areaPath} fill="url(#riskTrendFill)" />
            <path d={linePath} fill="none" stroke="#b45309" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
            {coordinates.map((point) => (
              <g key={point.label}>
                <circle cx={point.x} cy={point.y} fill="#fff7ed" r="4" stroke="#b45309" strokeWidth="2" />
              </g>
            ))}
          </svg>

          <div className="mt-3 flex justify-between text-[10px] uppercase tracking-wide text-slate-400">
            {trendPoints.map((point) => (
              <span key={point.label}>{point.label}</span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md bg-slate-50 px-3 py-2 text-slate-600">
            <span className="font-medium text-slate-700">Peak:</span> 83 at 10:00
          </div>
          <div className="rounded-md bg-slate-50 px-3 py-2 text-slate-600">
            <span className="font-medium text-slate-700">Direction:</span> easing after peak
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
