"use client";

import { Play, Send, Sparkles, TriangleAlert } from "lucide-react";

import { ApiAoi, ChatApiResult } from "../lib/api";
import { DownloadArtifactButton } from "./agent-chat/DownloadArtifactButton";
import { AgentWorkLog, ChatMessageBubble, InlineAgentTrace } from "./agent-chat/TraceDisplay";
import { downloadVisualization } from "./agent-chat/download";
import { loadingMessageForMessage } from "./agent-chat/traceHelpers";
import { prompts, useAgentChat } from "./agent-chat/useAgentChat";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function AgentChatBox({
  activeRunId,
  defaultRegionId = "live_australia",
  selectedRegion,
  externalAnswer,
  onNeedAoiFocus,
  onResult
}: {
  activeRunId?: string;
  defaultRegionId?: string;
  selectedRegion?: {
    regionId: string;
    regionName: string;
    aoi: ApiAoi;
  } | null;
  externalAnswer?: string;
  onNeedAoiFocus?: () => void;
  onResult?: (result: ChatApiResult) => void | Promise<void>;
}) {
  const {
    message,
    setMessage,
    answer,
    chatMessages,
    inlineTrace,
    generatedVisualization,
    isSubmitting,
    runningLogTick,
    intent,
    onSubmit
  } = useAgentChat({activeRunId, defaultRegionId, selectedRegion, externalAnswer, onNeedAoiFocus, onResult});

  return (
    <Card id="chat-panel" className="border-slate-200 shadow-sm">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Ask or command the agent</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">Operational</Badge>
            <Badge variant={intent === "action" ? "elevated" : intent === "analysis" ? "muted" : "outline"}>
              {intent === "action"
                ? "Action"
                : intent === "analysis"
                  ? "Analysis"
                  : intent === "visualization"
                    ? "Visualization"
                    : intent === "monitor"
                      ? "Monitor"
                      : "Question"}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {prompts.map((prompt) => (
            <Button key={prompt} size="sm" type="button" variant="outline" onClick={() => setMessage(prompt)}>
              <Sparkles className="mr-2 h-3.5 w-3.5" />
              {prompt}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="space-y-3" onSubmit={onSubmit}>
          <textarea
            aria-label="Agent command input"
            className="min-h-[112px] w-full resize-none rounded-lg border border-slate-200 bg-background px-3 py-3 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Why is the current risk moderate? What changes if wind speed increases by 20%? Which area should we inspect first?"
            value={message}
          />
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              {intent === "action" ? (
                <span className="inline-flex items-center gap-1">
                  <TriangleAlert className="h-3.5 w-3.5 text-orange-600" />
                  External actions still require approval before execution.
                </span>
              ) : intent === "analysis" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  {selectedRegion || activeRunId
                    ? "Analysis runs against the focused AOI and records Elastic MCP evidence when available."
                    : "Select a state and radius first. Analysis runs against the focused AOI."}
                </span>
              ) : intent === "visualization" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Creates a downloadable heatmap, contour GeoJSON, and AI map interpretation for the focused AOI.
                </span>
              ) : intent === "monitor" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Creates a recurring 10 minute risk monitor with alert-on-change behavior.
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Questions route through the existing `/api/chat` workflow.
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button disabled={isSubmitting} type="submit">
                <Send className="mr-2 h-4 w-4" />
                {isSubmitting ? "Running..." : "Send"}
              </Button>
            </div>
          </div>
        </form>

        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
          {chatMessages.length > 0 ? (
            <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
              {chatMessages.map((item) => (
                <ChatMessageBubble key={item.message_id} message={item} />
              ))}
              {isSubmitting ? (
                <div className="flex justify-start">
                  <AgentWorkLog items={inlineTrace} tick={runningLogTick} title={loadingMessageForMessage(message, intent)} />
                </div>
              ) : null}
            </div>
          ) : (
            <div>
              {isSubmitting ? <AgentWorkLog items={inlineTrace} tick={runningLogTick} title={answer} /> : answer}
            </div>
          )}
          {generatedVisualization ? (
            <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
                <div>
                  <div className="font-semibold text-slate-800">Hotspot visualization</div>
                  <div className="text-xs text-slate-500">Heatmap, contour preview, and AI interpretation</div>
                </div>
                <DownloadArtifactButton
                  label="Download hotspot visualization"
                  onClick={() => downloadVisualization(generatedVisualization)}
                />
              </div>
              {generatedVisualization.preview?.data_url ? (
                <div>
                  <img
                    alt={generatedVisualization.preview.alt || "Hotspot contour map preview"}
                    className="block max-h-[420px] w-full bg-slate-100 object-contain"
                    height={generatedVisualization.preview.height}
                    loading="lazy"
                    src={generatedVisualization.preview.data_url}
                    width={generatedVisualization.preview.width}
                  />
                </div>
              ) : null}
              <div className="px-3 py-2 text-xs leading-5 text-slate-500">
                Includes the contour map preview and a downloadable interpretation bundle.
              </div>
            </div>
          ) : null}
        </div>
        <InlineAgentTrace items={inlineTrace} isRunning={isSubmitting} tick={runningLogTick} />
      </CardContent>
    </Card>
  );
}
