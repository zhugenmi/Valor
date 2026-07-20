import { useCallback, useRef } from "react";
import type {
  AgentCompletedEvent,
  SystemFailedEvent,
  WorkflowCompletedEvent,
  WorkflowStartedEvent,
} from "@/app/analysis/constants";
import useSSE from "@/hooks/use-sse";
import { getServerUrl } from "@/lib/api-client";

export interface StreamAnalysisCallbacks {
  onWorkflowStarted?: (data: WorkflowStartedEvent) => void;
  onAgentCompleted?: (data: AgentCompletedEvent) => void;
  onWorkflowCompleted?: (data: WorkflowCompletedEvent) => void;
  onSystemFailed?: (data: SystemFailedEvent) => void;
  onError?: (error: Error) => void;
}

export interface UseStreamAnalysisReturn {
  startStream: (params: {
    ticker: string;
    startDate?: string;
    endDate?: string;
  }) => Promise<void>;
  isStreaming: boolean;
  close: () => void;
}

export function useStreamAnalysis(
  callbacks: StreamAnalysisCallbacks,
): UseStreamAnalysisReturn {
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  const { connect, close, isStreaming } = useSSE({
    url: getServerUrl("/agents/stream"),
    handlers: {
      onError: (error: Error) => {
        callbacksRef.current.onError?.(error);
      },
      onData: (sseData: { event: string; data: unknown }) => {
        const { event, data } = sseData;
        switch (event) {
          case "workflow_started":
            callbacksRef.current.onWorkflowStarted?.(
              data as unknown as WorkflowStartedEvent,
            );
            break;
          case "agent_completed":
            callbacksRef.current.onAgentCompleted?.(
              data as unknown as AgentCompletedEvent,
            );
            break;
          case "workflow_completed":
            callbacksRef.current.onWorkflowCompleted?.(
              data as unknown as WorkflowCompletedEvent,
            );
            break;
          case "system_failed":
            callbacksRef.current.onSystemFailed?.(
              data as unknown as SystemFailedEvent,
            );
            close();
            break;
          case "done":
            close();
            break;
          default:
            break;
        }
      },
    },
  });

  const startStream = useCallback(
    async (params: {
      ticker: string;
      startDate?: string;
      endDate?: string;
    }) => {
      const { ticker, startDate, endDate } = params;
      const body = JSON.stringify({
        query: ticker,
        agent_name: "ValorAgent",
        conversation_id: crypto.randomUUID(),
        start_date: startDate,
        end_date: endDate,
      });
      await connect(body);
    },
    [connect],
  );

  return { startStream, isStreaming, close };
}

export default useStreamAnalysis;
