import { links, site } from "./site";

export type Release = {
  version: string;
  page: string;
  installerUrl: string | null;
  sizeMb: number | null;
  date: string | null;
};

type GitHubAsset = { name: string; browser_download_url: string; size: number };

/**
 * Reads the newest GitHub Release on the server, at most once an hour (Next.js caches the fetch).
 * If GitHub cannot be reached, or no Release exists yet, it returns null and the page falls back to the Releases link,
 * so a download button is always present and the build never fails because of the network.
 */
export async function getLatestRelease(): Promise<Release | null> {
  try {
    const res = await fetch(`https://api.github.com/repos/${site.repo}/releases/latest`, {
      headers: { Accept: "application/vnd.github+json" },
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    const j = await res.json();
    const assets: GitHubAsset[] = Array.isArray(j.assets) ? j.assets : [];
    const exe = assets.find((a) => /setup.*\.exe$/i.test(a.name));
    return {
      version: String(j.tag_name ?? "").replace(/^v/, ""),
      page: typeof j.html_url === "string" ? j.html_url : links.releases,
      installerUrl: exe ? exe.browser_download_url : null,
      sizeMb: exe ? Math.round((exe.size / 1048576) * 10) / 10 : null,
      date: typeof j.published_at === "string" ? j.published_at.slice(0, 10) : null,
    };
  } catch {
    return null;
  }
}
