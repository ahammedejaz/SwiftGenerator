import { Page } from "@/components/studio/Chrome";
import { KnowledgeBase } from "@/components/studio/KnowledgeBase";

export const metadata = { title: "Knowledge Base · Financial Message Studio" };

export default function KnowledgeBasePage() {
  return (
    <Page
      title="Knowledge Base"
      lede="What has been indexed from the configured source roots, which messages that yields, and how the assistant is allowed to use it. Operator's view; nothing here is needed to generate a message."
      wide
    >
      <KnowledgeBase />
    </Page>
  );
}
