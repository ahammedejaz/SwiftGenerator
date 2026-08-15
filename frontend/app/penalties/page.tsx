import { PenaltyStudio } from "@/components/penalties/PenaltyStudio";

export default function PenaltiesPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Penalties module</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">MT537 penalty statements</h1>
      <p className="mt-4 max-w-4xl text-lg leading-8 text-slate-600">
        Report source-supplied settlement-fail or late-matching-fail penalties. This module does
        not calculate penalty amounts, and the LLM is never allowed to invent one.
      </p>
      <div className="mt-8"><PenaltyStudio /></div>
    </main>
  );
}
