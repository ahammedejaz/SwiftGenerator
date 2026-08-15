import { BulkGenerator } from "@/components/bulk/BulkGenerator";

export default function BulkPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Bulk Excel mode</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Generate a controlled test pack</h1>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
        Upload synthetic scenarios, continue past invalid rows, then download raw messages,
        validation JSON, summary Excel, and the overall execution report.
      </p>
      <div className="mt-8"><BulkGenerator /></div>
    </main>
  );
}
