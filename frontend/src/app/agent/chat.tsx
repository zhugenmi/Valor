import { Navigate, useParams } from "react-router";
import type { Route } from "./+types/chat";
import CommonAgentArea from "./components/agent-view/common-agent-area";

export default function AgentChat() {
  const { agentName } = useParams<Route.LoaderArgs["params"]>();

  if (!agentName) return <Navigate to="/" replace />;

  return (
    <main className="relative flex flex-1 flex-col overflow-hidden">
      {(() => {
        switch (agentName) {
          default:
            return <CommonAgentArea agentName={agentName} />;
        }
      })()}
    </main>
  );
}
