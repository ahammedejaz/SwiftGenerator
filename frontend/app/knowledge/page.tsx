import { KnowledgeCentre } from "@/components/knowledge/KnowledgeCentre";

export default function KnowledgePage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-700">
          Deterministic knowledge, no AI call
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Tag Intelligence Centre</h1>
        <p className="mt-4 max-w-3xl leading-7 text-slate-600">
          Explore concise, source-referenced business and technical metadata for every field emitted by the supported settlement composers.
        </p>
      </header>
      <KnowledgeCentre />
    </main>
  );
}
