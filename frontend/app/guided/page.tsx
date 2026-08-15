import { GuidedGenerator } from "@/components/guided/GuidedGenerator";

export default function GuidedPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
        Beginner guided mode
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Describe the settlement</h1>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
        Business language is interpreted into a typed scenario. Deterministic code then asks,
        resolves, validates, and composes the demonstration message.
      </p>
      <div className="mt-8"><GuidedGenerator /></div>
    </main>
  );
}
