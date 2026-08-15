import { MessageCatalogue } from "@/components/platform/MessageCatalogue";

export default function CataloguePage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Capability evidence</p>
      <h1 className="mt-2 text-3xl font-semibold">Message Catalogue</h1>
      <p className="mt-3 max-w-4xl leading-7 text-slate-600">
        Browse supported, partial, catalogue-only, and unavailable functions using measured
        configured-row coverage. Capability is never inferred from a mandatory-only golden path.
      </p>
      <div className="mt-8"><MessageCatalogue /></div>
    </main>
  );
}
