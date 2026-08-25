import type { ApiHotspotVisualization } from "../../lib/api";

export function downloadDataUrl(dataUrl: string, filename: string) {
  const [meta, encoded] = dataUrl.split(",");
  const mime = meta.match(/data:(.*?);base64/)?.[1] ?? "application/octet-stream";
  const binary = window.atob(encoded ?? "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  downloadBlob(new Blob([bytes], {type: mime}), filename);
}

export function downloadBlob(blob: Blob, filename: string) {
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

export function downloadVisualization(visualization: ApiHotspotVisualization) {
  if (visualization.preview?.data_url) {
    downloadDataUrl(visualization.preview.data_url, visualization.downloads.png_filename ?? "hotspot-contour-map.png");
  }
  const interpretation = visualization.downloads.txt_content ?? [
    visualization.interpretation.summary,
    visualization.interpretation.recommendation,
    visualization.interpretation.caveat
  ].join("\n\n");
  downloadBlob(new Blob([interpretation], {type: "text/plain;charset=utf-8"}), visualization.downloads.txt_filename ?? "hotspot-interpretation.txt");
}
