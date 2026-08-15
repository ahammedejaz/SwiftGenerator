import type { Metadata } from "next";
import { Chrome } from "@/components/studio/Chrome";
import "./globals.css";

export const metadata: Metadata = {
  title: "Financial Message Studio",
  description:
    "Produce valid SWIFT MT and ISO 20022 messages for testing — from the browser, from a spreadsheet, or from your pipeline.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Chrome>{children}</Chrome>
      </body>
    </html>
  );
}
