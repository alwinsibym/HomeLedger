import { LanguageProvider } from "@/components/LanguageProvider";
import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { TrustStrip } from "@/components/TrustStrip";
import { Features } from "@/components/Features";
import { Screens } from "@/components/Screens";
import { HowItWorks } from "@/components/HowItWorks";
import { Safety } from "@/components/Safety";
import { Shortcuts } from "@/components/Shortcuts";
import { Download } from "@/components/Download";
import { Faq } from "@/components/Faq";
import { Footer } from "@/components/Footer";
import { getLatestRelease } from "@/lib/release";

// Re-check GitHub for a new release at most once an hour; the page itself stays static and fast.
export const revalidate = 3600;

export default async function Home() {
  const release = await getLatestRelease();
  return (
    <LanguageProvider>
      <a className="skip" href="#features">Skip to content</a>
      <Header />
      <main>
        <Hero release={release} />
        <TrustStrip />
        <Features />
        <Screens />
        <HowItWorks />
        <Safety />
        <Shortcuts />
        <Download release={release} />
        <Faq />
      </main>
      <Footer />
    </LanguageProvider>
  );
}
