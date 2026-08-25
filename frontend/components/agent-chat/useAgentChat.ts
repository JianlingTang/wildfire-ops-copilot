import { FormEvent, useDeferredValue, useEffect, useState } from "react";

import { ApiAoi, ApiChatMessage, ApiHotspotVisualization, ChatApiResult, sendChat } from "../../lib/api";
import {
  ChatIntent,
  InlineTraceItem,
  classifyIntent,
  completedTraceForResult,
  loadingMessageForMessage,
  runningTraceForIntent
} from "./traceHelpers";

export const prompts = [
  "Analyze the most active hotspot region in Australia and generate today's report.",
  "Create a monitor task for this state every 10 minutes.",
  "Why is the current risk moderate?",
  "Show the risk trend for this AOI.",
  "What changes if wind speed increases by 20%?",
  "Which area should we inspect first? Show the five most exposed roads and assets nearby.",
  "Draft a public alert for Facebook, email, and an official advisory."
];

export type UseAgentChatOptions = {
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
};

export function useAgentChat({
  activeRunId,
  defaultRegionId = "live_australia",
  selectedRegion,
  externalAnswer,
  onNeedAoiFocus,
  onResult
}: UseAgentChatOptions) {
  const [message, setMessage] = useState(prompts[0]);
  const [answer, setAnswer] = useState("Ask the agent to analyze the region, answer a question, or draft an action.");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [latestRunId, setLatestRunId] = useState<string | undefined>();
  const [chatMessages, setChatMessages] = useState<ApiChatMessage[]>([]);
  const [inlineTrace, setInlineTrace] = useState<InlineTraceItem[]>([]);
  const [generatedVisualization, setGeneratedVisualization] = useState<ApiHotspotVisualization | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [runningLogTick, setRunningLogTick] = useState(0);
  const deferredMessage = useDeferredValue(message);
  const intent: ChatIntent = classifyIntent(deferredMessage);

  useEffect(() => {
    if (externalAnswer) {
      setAnswer(externalAnswer);
    }
  }, [externalAnswer]);

  useEffect(() => {
    if (!isSubmitting) {
      setRunningLogTick(0);
      return;
    }
    const timer = window.setInterval(() => {
      setRunningLogTick((current) => current + 1);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!activeRunId && !selectedRegion) {
      setAnswer("Select a state and radius, then focus the AOI before asking the agent.");
      setInlineTrace([
        {
          agent: "Main Coordinator",
          action: "Rejected request before tool calls",
          output: "Focus AOI is required",
          status: "failed"
        }
      ]);
      onNeedAoiFocus?.();
      return;
    }
    setIsSubmitting(true);
    setRunningLogTick(0);
    setAnswer(loadingMessageForMessage(message, intent));
    const optimisticUserMessage: ApiChatMessage = {
      message_id: `local-${Date.now()}`,
      conversation_id: conversationId ?? "pending",
      role: "user",
      content: message,
      intent,
      tool_trace: [],
      tool_results: {},
      run_id: activeRunId ?? latestRunId ?? null,
      region_id: selectedRegion?.regionId ?? defaultRegionId,
      created_at: new Date().toISOString()
    };
    setChatMessages((current) => [...current, optimisticUserMessage]);
    setGeneratedVisualization(null);
    setInlineTrace(runningTraceForIntent(intent));
    try {
      const result = await sendChat(message, {
        conversationId,
        runId: activeRunId ?? latestRunId,
        regionId: selectedRegion?.regionId ?? defaultRegionId,
        regionName: selectedRegion?.regionName,
        aoi: selectedRegion?.aoi
      });
      applyResult(result);
      await onResult?.(result);
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : "Chat request failed.");
      setInlineTrace([
        {
          agent: "Main Coordinator",
          action: "Request failed",
          output: error instanceof Error ? error.message : "Chat request failed",
          status: "failed"
        }
      ]);
    } finally {
      setIsSubmitting(false);
    }
  }

  function applyResult(result: ChatApiResult) {
    setAnswer(result.response?.answer ?? result.response?.safety_note ?? result.response?.message ?? "Request completed.");
    if (result.conversation_id) {
      setConversationId(result.conversation_id);
    }
    if (result.run?.run_id) {
      setLatestRunId(result.run.run_id);
    }
    if (result.messages?.length) {
      setChatMessages(result.messages);
    } else {
      setChatMessages((current) => [...current, assistantMessageFrom(result)]);
    }
    setInlineTrace(completedTraceForResult(result, intent));
    setGeneratedVisualization(result.response?.visualization ?? null);
  }

  function assistantMessageFrom(result: ChatApiResult): ApiChatMessage {
    return {
      message_id: `assistant-${Date.now()}`,
      conversation_id: result.conversation_id ?? conversationId ?? "local",
      role: "assistant",
      content: result.response?.answer ?? result.response?.safety_note ?? result.response?.message ?? "Request completed.",
      intent: result.intent,
      tool_trace: result.response?.tool_trace ?? [],
      tool_results: result.response?.tool_results ?? {},
      run_id: result.run?.run_id ?? activeRunId ?? latestRunId ?? null,
      region_id: selectedRegion?.regionId ?? defaultRegionId,
      created_at: new Date().toISOString()
    };
  }

  return {
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
  };
}
