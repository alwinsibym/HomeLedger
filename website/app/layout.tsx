import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { site } from "@/lib/site";
import "./globals.css";

const description =
  "HomeLedger is a free, offline accounting program for Windows with Tally-style keyboard entry, a dashboard, bill photos, backups, and a Malayalam guide. Your books never leave your computer.";

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: { default: "HomeLedger: offline accounts for your home", template: "%s | HomeLedger" },
  description,
  applicationName: site.name,
  keywords: ["accounting software", "offline accounting", "Windows", "household accounts", "ledger", "GST", "free"],
  openGraph: {
    type: "website",
    siteName: site.name,
    title: "HomeLedger: offline accounts for your home",
    description,
    url: "/",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "HomeLedger dashboard" }],
  },
  twitter: { card: "summary_large_image", title: "HomeLedger", description, images: ["/og.png"] },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = { themeColor: "#f2f0ea", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
