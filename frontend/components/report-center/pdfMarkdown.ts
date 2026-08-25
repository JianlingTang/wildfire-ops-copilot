// Parses the report's markdown body into the sections/metadata/citations
// used to lay out the PDF (pdfLayout.ts).

import { cleanPdfText } from "./pdfPrimitives";

export type ReportSection = {
  title: string;
  lines: string[];
};

export type Citation = {
  id: string;
  title: string;
};

export type Reference = {
  id: string;
  label: string;
  detail: string;
};

export function parseReportMarkdown(markdown: string) {
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
