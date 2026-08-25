import { Card, CardContent } from "../ui/card";

export function CompactSummaryStrip({
  hotspotCount,
  pendingApprovalCount,
  riskLevel,
  riskScore,
  warningCount
}: {
  hotspotCount: number;
  pendingApprovalCount: number;
  riskLevel: string;
  riskScore?: number | null;
  warningCount: number;
}) {
  const items = [
    {label: "Risk Score", value: riskScore != null ? `${riskScore}/100` : "--", tone: "text-slate-950"},
    {label: "Risk Level", value: riskLevel, tone: riskLevel === "HIGH" || riskLevel === "EXTREME" ? "text-red-700" : "text-slate-950"},
    {label: "Hotspots", value: String(hotspotCount), tone: "text-orange-700"},
    {label: "Warnings", value: String(warningCount), tone: warningCount > 0 ? "text-orange-700" : "text-slate-950"},
    {label: "Approvals", value: String(pendingApprovalCount), tone: pendingApprovalCount > 0 ? "text-orange-700" : "text-slate-950"}
  ];

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
        {items.map((item) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3" key={item.label}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{item.label}</div>
            <div className={`mt-2 text-2xl font-semibold ${item.tone}`}>{item.value}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
