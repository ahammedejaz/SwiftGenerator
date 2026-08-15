import { Page } from "@/components/studio/Chrome";
import { ExcelStudio } from "@/components/studio/ExcelStudio";

export const metadata = { title: "Bulk / Excel · Financial Message Studio" };

export default function ExcelPage() {
  return (
    <Page
      title="Bulk and Excel"
      lede="Keep scenario data in a spreadsheet and turn the whole workbook into messages in one step. The templates are generated from the message specification, so you never have to invent a tag or an element path."
      wide
    >
      <ExcelStudio />
    </Page>
  );
}
