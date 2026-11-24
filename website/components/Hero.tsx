"use client";

import { useRef } from "react";
import { useLang } from "./LanguageProvider";
import { useScrollProgress } from "@/hooks/useScrollProgress";
import { Icon } from "./Icon";
import { links } from "@/lib/site";
import type { Release } from "@/lib/release";

/**
 * One full-screen scene: colour field, headline, the app window and a few glass highlights.
 * On load the whole scene settles in from a zoom (see `.hero-zoom` and the html.pre / html.ready classes set by <Preloader>).
 * Scrolling then eases the frame away.
 */
export function Hero({ release }: { release: Release | null }) {
  const { t } = useLang();
  const h = t.hero;
  const ref = useRef<HTMLElement>(null);
  useScrollProgress(ref, (p) => ref.current?.style.setProperty("--hp", p.toFixed(3)));
  const href = release?.installerUrl ?? links.releases;

  return (
    <section ref={ref} className="hero" id="top">
      <div className="hero-frame">
        <div className="hero-zoom">
          <div className="scene" aria-hidden="true">
            <i className="b1" />
            <i className="b2" />
            <i className="b3" />
            <div className="grain" />
          </div>

          <div className="hero-body">
            <div className="hb-in">
              <p className="eyebrow light">{h.eyebrow}</p>
              <h1>
                <span className="h1-pre">{h.prefix}</span>
                <span className="h1-word">
                  {h.word}
                  <em>.</em>
                </span>
              </h1>
              <p className="hero-lead">{h.lead}</p>
              <div className="cta">
                <a className="pill light big" href={href}>
                  <Icon name="download" size={18} />
                  {release?.version ? h.downloadVersion(release.version) : h.download}
                </a>
                <a className="pill glass big" href={links.repo} target="_blank" rel="noopener noreferrer">
                  <Icon name="github" size={18} />
                  {h.github}
                </a>
              </div>
            </div>
          </div>

          <div className="device">
            <div className="device-bar" aria-hidden="true">
              <span><i /><i /><i /></span>
              <b>HomeLedger</b>
            </div>
            <div className="device-screens">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/screens/dashboard.webp" alt={h.alt} width={1280} height={800} loading="eager" decoding="async" fetchPriority="high" />
            </div>
            <div className="chip" aria-hidden="true">
              <span className="chip-dot"><Icon name="check" size={12} /></span>
              {h.chip}
            </div>
          </div>

          <div className="hero-stat">
            <strong>{h.stat.big}</strong>
            <span>{h.stat.text}</span>
            <small>{h.stat.note}</small>
          </div>

          <ul className="hero-cards" aria-label="Highlights">
            {h.cards.map((c) => (
              <li key={c.title} className="hcard">
                <kbd className="key on-dark">{c.key}</kbd>
                <span className="hcard-t">{c.title}</span>
                <span className="hcard-s">{c.text}</span>
              </li>
            ))}
          </ul>
        </div>

        <a className="scroll-hint" href="#hub" aria-label={h.scroll}>
          <span>{h.scroll}</span>
          <i />
        </a>
      </div>
    </section>
  );
}
