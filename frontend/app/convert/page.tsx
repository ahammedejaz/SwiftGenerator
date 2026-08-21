import { ConvertMessage } from "@/components/studio/ConvertMessage";
import { Page } from "@/components/studio/Chrome";

export const metadata = { title: "Convert Message · Financial Message Studio" };

export default function ConvertPage() {
  return (
    <Page
      title="Convert Message"
      lede="Transform business values from MT to MX through an explicit Mapping Pack, inspect every loss or derivation, then validate the target with the ordinary message engine."
      wide
    >
      <ConvertMessage />
    </Page>
  );
}
