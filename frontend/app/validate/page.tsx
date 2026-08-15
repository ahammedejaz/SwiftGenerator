import { Page } from "@/components/studio/Chrome";
import { ValidateStudio } from "@/components/studio/ValidateStudio";

export const metadata = { title: "Validate · Financial Message Studio" };

export default function ValidatePage() {
  return (
    <Page
      title="Validate a message"
      lede="Check field data or an existing MT message against the configured subset and your client profile. Nothing is saved and nothing is generated."
    >
      <ValidateStudio />
    </Page>
  );
}
