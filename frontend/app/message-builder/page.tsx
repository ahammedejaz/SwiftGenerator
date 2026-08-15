import { MessageBuilder } from "@/components/platform/MessageBuilder";

export default async function MessageBuilderPage({ searchParams }: { searchParams: Promise<{ messageType?: string }> }) {
  const params = await searchParams;
  return <main className="mx-auto max-w-7xl px-6 py-10"><p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Encrypted tenant workspace</p><h1 className="mt-2 text-3xl font-semibold">Secure Message Builder</h1><p className="mt-3 max-w-4xl leading-7 text-slate-600">Business and expert sequence views use the same source-bounded specification. No LLM participates in form rendering, composition, validation, or downloads.</p><div className="mt-8"><MessageBuilder initialMessageType={params.messageType} /></div></main>;
}
