"use client";

import { Download, FileText } from "lucide-react";

import { ApiReport } from "../lib/api";
import { downloadReportPdf } from "./report-center/buildReportPdf";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function ReportCenter({mode = "demo", reports = []}: {mode?: string; reports?: ApiReport[]}) {
  return (
    <Card id="reports-panel" className="border-slate-200 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Report Center</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{mode === "demo" ? "Operational" : "Live"}</Badge>
            <Badge variant="outline">PDF</Badge>
          </div>
        </div>
        <div className="text-xs text-slate-500">Reports include Elastic MCP policy, playbook, and historical evidence when available.</div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {reports.length ? (
          reports.map((report) => (
            <Card key={report.report_id}>
              <CardContent className="flex items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <FileText className="h-4 w-4" />
                    {report.title}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {report.type} · Generated · {formatTime(report.created_at)}
                  </div>
                  <div className="mt-2 text-xs text-slate-500">Includes Elastic MCP evidence in the briefing narrative.</div>
                </div>
                <Button size="sm" variant="outline" type="button" onClick={() => downloadReportPdf(report)}>
                  <Download className="mr-2 h-4 w-4" />
                  Download PDF
                </Button>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
            No reports yet. Ask the agent to analyze the region and generate today's report.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
