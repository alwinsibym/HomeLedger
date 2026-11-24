import { LanguageProvider } from "@/components/LanguageProvider";
import { MotionRoot } from "@/components/MotionRoot";
import { Preloader } from "@/components/Preloader";
import { PageGlow } from "@/components/PageGlow";
import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { Hub } from "@/components/Hub";
import { Bento } from "@/components/Bento";
import { Showcase } from "@/components/Showcase";
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
      <Preloader />
      <PageGlow />
      <Header />
      <main>
        <Hero release={release} />
        <Hub />
        <Bento />
        <Showcase />
        <HowItWorks />
        <Safety />
        <Shortcuts />
        <Download release={release} />
        <Faq />
      </main>
      <Footer />
      <MotionRoot />
    </LanguageProvider>
  );
}
