"use client";

import { useLang } from "./LanguageProvider";
import { AppFrame } from "./AppFrame";
import { Icon } from "./Icon";
import { links } from "@/lib/site";
import type { Release } from "@/lib/release";

export function Hero({ release }: { release: Release | null }) {
  const { t } = useLang();
  const href = release?.installerUrl ?? links.releases;
  return (
    <section className="hero" id="top">
      <div className="container hero-in">
        <div className="hero-copy">
          <p className="eyebrow">{t.hero.eyebrow}</p>
          <h1>{t.hero.title}</h1>
          <p className="lead">{t.hero.lead}</p>
          <div className="cta">
            <a className="btn primary" href={href}>
              <Icon name="download" />
              {release?.version ? t.hero.downloadVersion(release.version) : t.hero.download}
            </a>
            <a className="btn" href={links.repo} target="_blank" rel="noopener noreferrer">
              <Icon name="github" />
              {t.hero.github}
            </a>
          </div>
          <ul className="meta">
            {t.hero.meta.map((m) => (
              <li key={m}>
                <Icon name="check" size={16} />
                {m}
              </li>
            ))}
          </ul>
        </div>
        <div className="hero-shot">
          <AppFrame src="/screens/gateway.webp" alt={t.hero.alt} priority />
        </div>
      </div>
    </section>
  );
}
