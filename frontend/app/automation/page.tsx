import { Page } from "@/components/studio/Chrome";
import { Automation } from "@/components/studio/Automation";

export const metadata = { title: "API & Automation · Financial Message Studio" };

export default function AutomationPage() {
  return (
    <Page
      title="API and automation"
      lede="Everything the browser can do, your pipeline can do. Send tag or element data, or upload a spreadsheet, and get a complete FIN message or ISO 20022 XML back."
      wide
    >
      <Automation />
    </Page>
  );
}
