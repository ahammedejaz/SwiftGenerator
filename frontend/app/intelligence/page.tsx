import { Page } from "@/components/studio/Chrome";
import { Intelligence } from "@/components/studio/Intelligence";

export const metadata = { title: "Message Intelligence · Financial Message Studio" };

export default function IntelligencePage() {
  return (
    <Page
      title="Message Intelligence"
      lede="Look up any MT tag or ISO 20022 element and find out what it means, why it is used, how it is formatted and what it looks like inside a real message."
      wide
    >
      <Intelligence />
    </Page>
  );
}
