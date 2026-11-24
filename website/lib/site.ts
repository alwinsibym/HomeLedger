/**
 * The few facts that appear in many places. Change them here and the whole page follows.
 * `publisher` is the name shown in the footer; keep it equal to the name used in the Windows installer.
 */
export const site = {
  name: "HomeLedger",
  publisher: "HomeLedger",
  repo: "alwinsibym/HomeLedger",
  url: "https://homeledger.vercel.app",
  year: 2026,
} as const;

export const links = {
  repo: `https://github.com/${site.repo}`,
  releases: `https://github.com/${site.repo}/releases/latest`,
  issues: `https://github.com/${site.repo}/issues`,
  changelog: `https://github.com/${site.repo}/releases`,
  guideEn: "/guides/HomeLedger_Guide.pdf",
  guideMl: "/guides/HomeLedger_Guide_Malayalam.pdf",
  guideMd: `https://github.com/${site.repo}/blob/main/docs/USER_GUIDE.md`,
} as const;
