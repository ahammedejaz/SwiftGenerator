import { Page } from "@/components/studio/Chrome";
import { RecentMessages } from "@/components/studio/RecentMessages";

export const metadata = { title: "Recent Messages · Financial Message Studio" };

export default function RecentPage() {
  return (
    <Page
      title="Recent messages"
      lede="Everything generated recently — from the browser, from a spreadsheet or from a pipeline — so you can download it again without rebuilding the scenario."
      wide
    >
      <RecentMessages />
    </Page>
  );
}
