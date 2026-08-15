import { OperationsConsole } from "@/components/platform/OperationsConsole";

export default function OperationsPage() {
  return <main className="mx-auto max-w-5xl px-6 py-10"><p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Controlled operations</p><h1 className="mt-2 text-3xl font-semibold">Review, Approval, and Submission</h1><p className="mt-3 max-w-3xl leading-7 text-slate-600">An immutable checksum-bound revision must pass local gates, external-evidence policy, maker-checker approval, connector allowlisting, and idempotency controls.</p><div className="mt-8"><OperationsConsole /></div></main>;
}
