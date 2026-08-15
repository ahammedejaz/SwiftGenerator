import Link from "next/link";

const actions = [
  {
    title: "Message Catalogue",
    description: "Review capability and measured configured-row coverage for every message.",
    href: "/catalogue",
  },
  {
    title: "Secure Message Builder",
    description: "Author encrypted, tenant-scoped real-data drafts in business or sequence mode.",
    href: "/message-builder",
  },
  {
    title: "Annotated Samples",
    description: "Inspect composer-generated synthetic messages with line-by-line Tag Intelligence.",
    href: "/samples",
  },
  {
    title: "Operations",
    description: "Review validation, approvals, configured connectors, and submission evidence.",
    href: "/operations",
  },
  {
    title: "Lifecycle demo",
    description: "Run the complete MT541 to MT548 to MT545 correlated lifecycle.",
    href: "/lifecycle",
  },
  {
    title: "Guided generation",
    description: "Describe a settlement in business language and answer friendly questions.",
    href: "/guided",
  },
  {
    title: "Expert builder",
    description: "Inspect canonical fields, deterministic tags, and the raw demonstration message.",
    href: "/expert",
  },
  {
    title: "Bulk generator",
    description: "Generate and validate multiple synthetic scenarios from an Excel workbook.",
    href: "/bulk",
  },
  {
    title: "Tag Intelligence",
    description: "Understand verified tag meanings, conditions, dependencies, and profile rules without an AI call.",
    href: "/knowledge",
  },
  {
    title: "Settlement Processing",
    description: "Decide amendments, create a verified MT530 priority command, or cancel and rebook.",
    href: "/settlement-processing",
  },
  {
    title: "Penalty Statements",
    description: "Build a source-bounded MT537 statement from supplied synthetic penalty amounts.",
    href: "/penalties",
  },
  {
    title: "Corporate Actions",
    description: "Run a source-bounded MT564 → MT565 → MT567 → MT566 lifecycle with MT568 narrative.",
    href: "/corporate-actions",
  },
  {
    title: "AI Efficiency",
    description: "Review content-free live API, token, cost, latency, and exact-cache efficiency metrics.",
    href: "/ai-efficiency",
  },
];

export default function Dashboard() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-12">
      <section className="rounded-3xl bg-slate-900 px-8 py-12 text-white shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-300">
          Controlled message engineering
        </p>
        <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-tight md:text-6xl">
          Author, validate, evidence, and control supported ISO 15022 messages.
        </h1>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-300">
          Actual client values remain inside the protected deterministic platform. Capability,
          provenance, validation levels, approval state, and connector readiness are explicit.
        </p>
      </section>

      <section aria-labelledby="workflows" className="py-10">
        <h2 id="workflows" className="text-2xl font-semibold">
          Workflows
        </h2>
        <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {actions.map((action) => (
            <Link
              key={action.title}
              href={action.href}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
            >
              <h3 className="text-lg font-semibold text-teal-800">{action.title}</h3>
              <p className="mt-3 leading-7 text-slate-600">{action.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
