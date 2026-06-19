"use client";

import { Download, FileText } from "lucide-react";

import { ApiReport } from "../lib/api";
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

function downloadReportPdf(report: ApiReport) {
  const pdf = buildReportPdf(report);
  downloadBlob(new Blob([pdf], {type: "application/pdf"}), `${safeFilename(report.title)}-${report.run_id}.pdf`);
}

type ReportSection = {
  title: string;
  lines: string[];
};

type Citation = {
  id: string;
  title: string;
};

type Reference = {
  id: string;
  label: string;
  detail: string;
};

type PdfTextBlock = {
  text: string;
  size?: number;
  font?: "regular" | "bold";
  color?: [number, number, number];
  indent?: number;
  gapBefore?: number;
  maxChars?: number;
};

function buildReportPdf(report: ApiReport) {
  const parsed = parseReportMarkdown(report.markdown);
  const contentStreams = layoutReportPages(report, parsed);
  const objects: string[] = [];
  objects.push("<< /Type /Catalog /Pages 2 0 R >>");
  const pageObjectIds = contentStreams.map((_, index) => 5 + index * 2);
  objects.push(`<< /Type /Pages /Kids [${pageObjectIds.map((id) => `${id} 0 R`).join(" ")}] /Count ${contentStreams.length} >>`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>");
  contentStreams.forEach((content, index) => {
    const pageId = 5 + index * 2;
    const contentId = pageId + 1;
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${contentId} 0 R >>`);
    objects.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  });
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.slice(1).forEach((offset) => {
    pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return pdf;
}

function parseReportMarkdown(markdown: string) {
  const sections: ReportSection[] = [];
  let current: ReportSection | null = null;
  markdown.split("\n").forEach((rawLine) => {
    const line = cleanPdfText(rawLine.trim());
    if (line.startsWith("# ")) {
      return;
    }
    if (line.startsWith("## ")) {
      current = {title: line.replace(/^##\s+/, ""), lines: []};
      sections.push(current);
      return;
    }
    if (current && line) {
      current.lines.push(line.replace(/^-\s+/, ""));
    }
  });
  const metadata = {
    region: metadataValue(markdown, "Region") ?? "Operational AOI",
    runId: metadataValue(markdown, "Run ID") ?? "unknown",
    risk: metadataValue(markdown, "Risk") ?? "Not scored"
  };
  const citations = citationSection(sections);
  const references = referenceList(sections, citations);
  return {sections, metadata, citations, references};
}

function metadataValue(markdown: string, label: string) {
  const match = markdown.match(new RegExp(`^${label}:\\s*(.+)$`, "m"));
  return match?.[1]?.trim();
}

function citationSection(sections: ReportSection[]): Citation[] {
  const section = sections.find((item) => item.title.toLowerCase() === "elastic files cited");
  if (!section) {
    return [];
  }
  return section.lines
    .map((line) => {
      const [rawId, ...rest] = line.split(":");
      const id = rawId.trim();
      const rawTitle = rest.join(":").trim();
      const title = rawTitle.split(" - ")[0].trim() || id;
      return {id, title: title.replace(/^[-\s]+/, "")};
    })
    .filter((item) => item.id);
}

function referenceList(sections: ReportSection[], citations: Citation[]): Reference[] {
  const references: Reference[] = [];
  const evidence = sections.find((item) => item.title.toLowerCase() === "evidence used");
  evidence?.lines.forEach((line) => {
    const [label, ...rest] = line.split(":");
    references.push({
      id: `R${references.length + 1}`,
      label: label.trim() || "Evidence",
      detail: rest.join(":").trim() || line
    });
  });
  citations.forEach((citation) => {
    references.push({
      id: `R${references.length + 1}`,
      label: citation.id,
      detail: citation.title
    });
  });
  return references;
}

function layoutReportPages(report: ApiReport, parsed: ReturnType<typeof parseReportMarkdown>) {
  const pages: string[] = [];
  let commands = pageHeader(report, parsed.metadata, 1);
  let y = 632;

  const addBlock = (block: PdfTextBlock) => {
    const size = block.size ?? 10;
    const lineHeight = Math.round(size * 1.45);
    y -= block.gapBefore ?? 0;
    const lines = wrapText(cleanPdfText(block.text), block.maxChars ?? (block.indent ? 74 : 86));
    lines.forEach((line) => {
      if (y < 62) {
        commands += pageFooter(pages.length + 1);
        pages.push(commands);
        commands = pageHeader(report, parsed.metadata, pages.length + 1);
        y = 632;
      }
      commands += textCommand(line, 54 + (block.indent ?? 0), y, size, block.font ?? "regular", block.color ?? [0.12, 0.16, 0.23]);
      y -= lineHeight;
    });
  };

  const summary = executiveSummary(parsed);
  addBlock({text: "Executive Summary", size: 15, font: "bold", gapBefore: 0, maxChars: 70});
  addBlock({text: summary, size: 10, color: [0.24, 0.29, 0.38], maxChars: 88});

  visibleSections(parsed).forEach((section) => {
    addBlock({text: section.title, size: 13, font: "bold", gapBefore: 12, maxChars: 76});
    section.lines.slice(0, section.title.toLowerCase() === "top risk drivers" ? 5 : 7).forEach((line) =>
      addBlock({text: `- ${line}`, size: 9.5, indent: 10, color: [0.22, 0.27, 0.35], maxChars: 82})
    );
  });

  addBlock({text: "References", size: 13, font: "bold", gapBefore: 12});
  if (parsed.references.length) {
    parsed.references.forEach((reference) =>
      addBlock({
        text: `[${reference.id}] ${reference.label}: ${reference.detail}`,
        size: 8.7,
        indent: 10,
        color: [0.23, 0.29, 0.39],
        maxChars: 84
      })
    );
  } else {
    addBlock({text: "No references were cited in this run.", size: 9.5, indent: 10, color: [0.35, 0.39, 0.47]});
  }

  addBlock({text: "Closing Summary", size: 13, font: "bold", gapBefore: 12});
  addBlock({
    text: finalSummary(parsed),
    size: 10,
    color: [0.22, 0.27, 0.35],
    maxChars: 88
  });

  commands += pageFooter(pages.length + 1);
  pages.push(commands);
  return pages;
}

function visibleSections(parsed: ReturnType<typeof parseReportMarkdown>) {
  const allowed = ["top risk drivers", "assets and monitoring", "recommended actions", "limitations"];
  return parsed.sections.filter((section) => allowed.includes(section.title.toLowerCase()));
}

function pageHeader(report: ApiReport, metadata: ReturnType<typeof parseReportMarkdown>["metadata"], pageNumber: number) {
  const generated = new Date(report.created_at).toLocaleString("en-AU");
  const region = truncateText(metadata.region, 42);
  const risk = truncateText(metadata.risk, 26);
  return [
    "0.06 0.10 0.18 rg 0 686 612 106 re f",
    "0.95 0.35 0.10 rg 42 730 34 34 re f",
    textCommand("WO", 50, 741, 12, "bold", [1, 1, 1]),
    textCommand("Wildfire Ops", 88, 758, 10, "bold", [0.89, 0.93, 0.98]),
    textCommand("Daily Wildfire", 88, 738, 19, "bold", [1, 1, 1]),
    textCommand("Operations Brief", 88, 717, 19, "bold", [1, 1, 1]),
    "0.10 0.15 0.25 rg 370 708 198 48 re f",
    textCommand(`Region: ${region}`, 384, 746, 8, "regular", [0.88, 0.92, 0.97]),
    textCommand(`Risk: ${risk}`, 384, 730, 9, "bold", [1, 0.90, 0.72]),
    textCommand(`Generated: ${generated}`, 384, 714, 7.7, "regular", [0.78, 0.84, 0.92]),
    "0.93 0.96 1 rg 42 656 528 22 re f",
    textCommand(`Report ${shortId(report.report_id)}  |  Run ${shortId(metadata.runId)}  |  Page ${pageNumber}`, 54, 663, 8.3, "regular", [0.25, 0.32, 0.44])
  ].join("\n");
}

function pageFooter(pageNumber: number) {
  return [
    "0.86 0.89 0.94 RG 42 42 m 570 42 l S",
    textCommand("Generated by Wildfire Ops Copilot. Operational intelligence only; verify before external action.", 42, 26, 8, "regular", [0.42, 0.47, 0.56]),
    textCommand(`Page ${pageNumber}`, 540, 26, 8, "regular", [0.42, 0.47, 0.56])
  ].join("\n");
}

function textCommand(text: string, x: number, y: number, size: number, font: "regular" | "bold", color: [number, number, number]) {
  return `BT ${color.join(" ")} rg /${font === "bold" ? "F2" : "F1"} ${size} Tf ${x} ${y} Td (${escapePdf(text)}) Tj ET\n`;
}

function wrapText(text: string, maxLength: number) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  words.forEach((word) => {
    if (`${current} ${word}`.trim().length > maxLength) {
      if (current) {
        lines.push(current);
      }
      current = word;
      return;
    }
    current = `${current} ${word}`.trim();
  });
  if (current) {
    lines.push(current);
  }
  return lines.length ? lines : [""];
}

function executiveSummary(parsed: ReturnType<typeof parseReportMarkdown>) {
  const recommendations = parsed.sections.find((section) => section.title.toLowerCase() === "recommended actions")?.lines ?? [];
  const firstRecommendation = (recommendations[0] ?? "Continue monitoring the selected AOI and review evidence before external action.").replace(/[.]+$/, "");
  const referenceText = parsed.references.length ? ` Supporting evidence is cited in References R1-R${parsed.references.length}.` : "";
  return `${parsed.metadata.region} is assessed at ${parsed.metadata.risk}. Primary operator focus: ${firstRecommendation}.${referenceText}`;
}

function finalSummary(parsed: ReturnType<typeof parseReportMarkdown>) {
  const referenceCount = parsed.references.length;
  return `Use this brief as the operational handoff for the current run. Prioritize recommended monitoring, refresh live hotspot and weather evidence before external action, and treat ${referenceCount} reference${referenceCount === 1 ? "" : "s"} as supporting context rather than official public warning material.`;
}

function truncateText(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
}

function shortId(value: string) {
  return value.length > 18 ? value.slice(0, 18) : value;
}

function cleanPdfText(value: string) {
  return value.replace(/[–—]/g, "-").replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "");
}

function escapePdf(value: string) {
  return value.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}

function safeFilename(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "report";
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
