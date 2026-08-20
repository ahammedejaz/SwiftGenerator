import { AiEfficiencyDashboard } from "@/components/ai/AiEfficiencyDashboard";
import { KnowledgeTelemetryPanel } from "@/components/ai/KnowledgeTelemetryPanel";

export default function AiEfficiencyPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-700">Content-free telemetry</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">AI Efficiency</h1>
        <p className="mt-4 max-w-3xl leading-7 text-slate-600">
          See live calls, exact-cache reuse, new token consumption, and usage avoided without exposing prompt or financial content.
        </p>
      </header>
      <AiEfficiencyDashboard />
      <div className="mt-7">
        <KnowledgeTelemetryPanel />
      </div>
    </main>
  );
}
