// Low-level PDF text/string helpers used by pdfLayout.ts to hand-roll a PDF
// content stream (no external PDF library dependency).

export function textCommand(text: string, x: number, y: number, size: number, font: "regular" | "bold", color: [number, number, number]) {
  return `BT ${color.join(" ")} rg /${font === "bold" ? "F2" : "F1"} ${size} Tf ${x} ${y} Td (${escapePdf(text)}) Tj ET\n`;
}

export function wrapText(text: string, maxLength: number) {
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

export function truncateText(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
}

export function shortId(value: string) {
  return value.length > 18 ? value.slice(0, 18) : value;
}

export function cleanPdfText(value: string) {
  return value.replace(/[–—]/g, "-").replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "");
}

function escapePdf(value: string) {
  return value.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}
