import { CorporateActionStudio } from "@/components/corporate-actions/CorporateActionStudio";

export default function CorporateActionsPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
        Corporate Actions · verified demonstration slice
      </p>
      <h1 className="mt-3 text-3xl font-semibold">Dividend-with-options lifecycle</h1>
      <p className="mt-3 max-w-4xl text-slate-600">
        Create a synthetic MT564 notification, MT565 cash election, MT567 processing status,
        MT566 cash confirmation, and associated MT568 narrative. Deterministic rules own every
        message field and lifecycle link.
      </p>
      <CorporateActionStudio />
    </main>
  );
}
