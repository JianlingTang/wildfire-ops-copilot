import type { ApiAction, ApiRun } from "../../lib/api";

export async function downloadApprovedAdvisoryAssets(action: ApiAction, run?: ApiRun | null) {
  const postText = buildFacebookPost(action, run);
  const text = [
    action.title,
    "",
    "Approved public advisory draft:",
    action.draft,
    "",
    "Facebook-ready post:",
    postText,
    "",
    `Approval status: ${action.status}`,
  ].join("\n");
  downloadTextFile(`${safeFilename(action.title)}.txt`, text);
  await downloadPosterPng(action, postText, run);
}

function buildFacebookPost(action: ApiAction, run?: ApiRun | null) {
  const risk = run?.risk_level && run?.risk_score != null ? `${run.risk_level} (${run.risk_score}/100)` : "current wildfire conditions";
  return `${action.draft}\n\nCurrent risk: ${risk}. Follow official emergency channels for updates.`;
}

function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function downloadPosterPng(action: ApiAction, postText: string, run?: ApiRun | null) {
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1080;
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  paintPosterBackground(context, canvas.width);
  context.fillStyle = "#0f172a";
  context.font = "700 38px Arial";
  wrapCanvasText(context, action.title, 60, 305, 950, 48, 2);
  context.font = "400 30px Arial";
  context.fillStyle = "#334155";
  wrapCanvasText(context, postText, 60, 430, 950, 42, 9);
  context.fillStyle = "#475569";
  context.font = "700 28px Arial";
  const risk = run?.risk_level && run?.risk_score != null ? `Risk: ${run.risk_level} ${run.risk_score}/100` : "Risk: latest approved advisory";
  context.fillText(risk, 60, 980);
  const url = canvas.toDataURL("image/png");
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeFilename(action.title)}-poster.png`;
  anchor.click();
}

function paintPosterBackground(context: CanvasRenderingContext2D, width: number) {
  context.fillStyle = "#f8fafc";
  context.fillRect(0, 0, width, 1080);
  context.fillStyle = "#0f172a";
  context.fillRect(0, 0, width, 150);
  context.fillStyle = "#ffffff";
  context.font = "700 42px Arial";
  context.fillText("Approved Public Advisory", 60, 92);
  context.fillStyle = "#ea580c";
  context.fillRect(60, 195, 160, 42);
  context.fillStyle = "#ffffff";
  context.font = "700 24px Arial";
  context.fillText("APPROVED", 82, 225);
}

function wrapCanvasText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number
) {
  const words = text.split(/\s+/);
  let line = "";
  let lineCount = 0;
  for (const word of words) {
    const nextLine = line ? `${line} ${word}` : word;
    if (context.measureText(nextLine).width > maxWidth && line) {
      context.fillText(line, x, y);
      y += lineHeight;
      line = word;
      lineCount += 1;
      if (lineCount >= maxLines) {
        return;
      }
    } else {
      line = nextLine;
    }
  }
  if (line && lineCount < maxLines) {
    context.fillText(line, x, y);
  }
}

function safeFilename(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "public-advisory";
}
