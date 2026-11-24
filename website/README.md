# HomeLedger website

The landing page for [HomeLedger](https://github.com/alwinsibym/HomeLedger): a small, fast Next.js (App Router, React, TypeScript) site with no database and no tracking. The program itself is a Windows desktop app that never goes online; this site only introduces it and links to the installer.

## Run it

```bash
cd website
npm install
npm run dev        # http://localhost:3000
npm run build      # production build
```

## Deploy on Vercel

1. Import the GitHub repository in Vercel.
2. Set **Root Directory** to `website`. Vercel detects Next.js and needs no other settings.
3. Deploy. Every push to `main` redeploys.

If you use a custom domain, put it in `lib/site.ts` (`url`).

## How it is organised

| Path | What it holds |
|---|---|
| `lib/site.ts` | Name, publisher, repository, links. Edit here first. |
| `lib/release.ts` | Looks up the newest GitHub Release (cached for an hour) so the button always downloads the current installer. Falls back to the Releases page. |
| `content/copy.ts` | Every word on the page, in English and Malayalam. |
| `components/` | One component per section (`Hero`, `Features`, `Screens`, `Safety`, `Download`, `Faq`, ...), plus `Section`, `Icon`, `AppFrame` and the language switch. |
| `app/` | `layout.tsx` (metadata and Open Graph), `page.tsx` (the order of sections), `globals.css` (theme), `robots.ts`, `sitemap.ts`. |
| `public/` | Logo, Open Graph image and the screenshots (made-up household data). |

## Editing

- **Change wording:** `content/copy.ts`. Add the same key to both languages (TypeScript will remind you).
- **Change colours:** the variables at the top of `app/globals.css`.
- **Add a screenshot tab:** put `name.webp` in `public/screens/` and add an entry to `screens.tabs` in both languages.
- **Publisher name:** `site.publisher` in `lib/site.ts`. Keep it the same as in `installer/HomeLedger.iss`.
