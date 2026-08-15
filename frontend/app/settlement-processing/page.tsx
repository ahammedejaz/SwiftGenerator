import { SettlementProcessingStudio } from "@/components/settlement-processing/SettlementProcessingStudio";

export default function SettlementProcessingPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
        Source-bounded processing controls
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">
        Cancellation, MT530 priority, and cancel/rebook
      </h1>
      <p className="mt-4 max-w-4xl text-lg leading-8 text-slate-600">
        A deterministic policy decides whether a requested change uses the verified MT530
        priority subset, cancellation and rebooking, or is unsupported. MT530 is not presented as
        a universal amendment message.
      </p>
      <div className="mt-8">
        <SettlementProcessingStudio />
      </div>
    </main>
  );
}
