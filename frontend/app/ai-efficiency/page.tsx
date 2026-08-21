import { KnowledgeTelemetryPanel } from "@/components/ai/KnowledgeTelemetryPanel";
import { Page } from "@/components/studio/Chrome";

export const metadata = { title: "AI & Knowledge Usage · Financial Message Studio" };

export default function AiEfficiencyPage() {
  return (
    <Page
      title="AI & Knowledge Usage"
      lede="Operational counts for model calls, retrieval, embeddings, caches and knowledge synchronization. Telemetry contains identifiers and counters, never financial content."
      wide
    >
      <KnowledgeTelemetryPanel />
    </Page>
  );
}
