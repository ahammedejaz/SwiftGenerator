import { ReportViewer } from "@/components/reports/ReportViewer";

export default async function ReportPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = await params;
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Audit report</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Bulk execution report</h1>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
        Review resolved messages, profile versions, row-level findings, and expected versus actual outcomes.
      </p>
      <div className="mt-8"><ReportViewer reportId={reportId} /></div>
    </main>
  );
}
