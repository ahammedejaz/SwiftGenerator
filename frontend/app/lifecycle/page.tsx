import { LifecycleStudio } from "@/components/lifecycle/LifecycleStudio";

export default function LifecyclePage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
        Minimum complete lifecycle
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">
        MT541 → MT548 → MT545
      </h1>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
        Generate a synthetic Receive Against Payment instruction, then produce controlled
        processing advice and a correlated full or partial confirmation.
      </p>
      <div className="mt-8">
        <LifecycleStudio />
      </div>
    </main>
  );
}
