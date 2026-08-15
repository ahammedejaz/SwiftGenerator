import { ExpertBuilder } from "@/components/expert/ExpertBuilder";

export default function ExpertPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
        Expert mode
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Inspect deterministic output</h1>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
        Compare the business object, fixed sequence/tag map, and raw supported-subset message.
      </p>
      <div className="mt-8"><ExpertBuilder /></div>
    </main>
  );
}
