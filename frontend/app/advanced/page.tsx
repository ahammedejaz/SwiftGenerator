import Link from "next/link";
import { Page } from "@/components/studio/Chrome";
import { Icon } from "@/components/studio/Icon";
import { Panel } from "@/components/studio/ui";

export const metadata = { title: "Advanced workflows · Financial Message Studio" };

/**
 * The specialist screens that predate the studio. They still work and are still needed for
 * lifecycle, penalties and corporate-action demonstrations — they are simply not the front
 * door, because a new tester should not have to choose between thirteen things.
 */
const GROUPS: Array<{
  title: string;
  description: string;
  items: Array<{ href: string; label: string; body: string }>;
}> = [
  {
    title: "Message lifecycles",
    description:
      "Correlated multi-message flows, where one message answers another and the platform checks the linkage.",
    items: [
      {
        href: "/lifecycle",
        label: "Settlement lifecycle",
        body: "Run MT541 → MT548 → MT545 and inspect the correlation between them.",
      },
      {
        href: "/settlement-processing",
        label: "Settlement processing",
        body: "Classify an amendment, issue an MT530 priority command, or cancel and rebook.",
      },
      {
        href: "/corporate-actions",
        label: "Corporate actions",
        body: "MT564 → MT565 → MT567 → MT566, with an MT568 narrative.",
      },
      {
        href: "/penalties",
        label: "Penalty statements",
        body: "Build an MT537 statement from supplied penalty amounts.",
      },
    ],
  },
  {
    title: "Authoring and operations",
    description:
      "The tenant-scoped, role-based authoring stack: encrypted drafts, maker-checker approval and controlled submission.",
    items: [
      {
        href: "/message-builder",
        label: "Secure message builder",
        body: "Author an encrypted, tenant-scoped draft in business or sequence mode.",
      },
      {
        href: "/operations",
        label: "Operations console",
        body: "Review validation levels, approvals, configured connectors and submission evidence.",
      },
      {
        href: "/catalogue",
        label: "Message catalogue",
        body: "Capability and measured configured-row coverage for every message type.",
      },
      {
        href: "/samples",
        label: "Annotated samples",
        body: "Composer-generated samples with line-by-line field annotations.",
      },
    ],
  },
  {
    title: "AI assistance",
    description:
      "The model interprets business intent. It never renders, validates or parses a message — those are always deterministic.",
    items: [
      {
        href: "/guided",
        label: "Describe a scenario",
        body: "Write a settlement in plain English and let the model propose the canonical fields.",
      },
      {
        href: "/expert",
        label: "Canonical field inspector",
        body: "Inspect the canonical scenario, the deterministic tags and the raw message together.",
      },
      {
        href: "/knowledge",
        label: "Tag Intelligence (original)",
        body: "The MT-only knowledge browser that Message Intelligence extends.",
      },
      {
        href: "/ai-efficiency",
        label: "AI efficiency",
        body: "Live API calls, cache hits, tokens, cost, latency and what was avoided.",
      },
    ],
  },
];

export default function AdvancedPage() {
  return (
    <Page
      title="Advanced workflows"
      lede="Specialist screens for lifecycle demonstrations, the authoring and approval stack, and AI assistance. Everything here still works; none of it is needed to generate a message."
    >
      <div className="space-y-6">
        {GROUPS.map((group) => (
          <Panel
            key={group.title}
            title={group.title}
            description={group.description}
            bodyClassName="px-0 py-0"
          >
            <ul className="divide-y divide-line">
              {group.items.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="group flex items-start gap-4 px-5 py-3.5 transition-colors duration-150 hover:bg-rail"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block text-[0.9375rem] font-medium">{item.label}</span>
                      <span className="mt-0.5 block text-sm leading-6 text-ink-2">
                        {item.body}
                      </span>
                    </span>
                    <Icon
                      name="chevron-right"
                      className="mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>
    </Page>
  );
}
