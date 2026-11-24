"use client";

import { useEffect, useRef, useState } from "react";
import { useLang } from "./LanguageProvider";
import { useScrollProgress } from "@/hooks/useScrollProgress";
import { Icon } from "./Icon";
import { links } from "@/lib/site";
import type { Release } from "@/lib/release";

const screens = ["dashboard", "payment", "billinbox", "utilities"] as const;

/**
 * Full-screen hero. The headline word rolls every few seconds; the colour field behind it, the app window and the small
 * card on the right all follow the same step. Keyboard focus inside the hero pauses it. Scrolling eases the whole frame away.
 */
export function Hero({ release }: { release: Release | null }) {
  const { t } = useLang();
  const h = t.hero;
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const n = h.words.length;

  useEffect(() => {
    if (paused || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => setI((v) => (v + 1) % n), 4200);
    return () => window.clearInterval(id);
  }, [paused, n]);

  useScrollProgress(ref, (p) => ref.current?.style.setProperty("--hp", p.toFixed(3)));

  const href = release?.installerUrl ?? links.releases;
  const pos = (k: number) => (k === i ? "on" : k === (i - 1 + n) % n ? "out" : "wait");

  return (
    <section ref={ref} className="hero" id="top" onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}>
      <div className="hero-frame">
        <div className="scenes" aria-hidden="true">
          {h.words.map((w, k) => (
            <div key={w} className={`scene s${k} ${k === i ? "on" : ""}`}>
              <i className="b1" />
              <i className="b2" />
              <i className="b3" />
            </div>
          ))}
          <div className="grain" />
        </div>

        <div className="hero-body">
          <p className="eyebrow light">{h.eyebrow}</p>
          <h1 aria-label={`${h.prefix} ${h.words[i]}`}>
            <span className="h1-pre">{h.prefix}</span>
            <span className="roll" aria-hidden="true">
              {h.words.map((w, k) => (
                <span key={w} className={`roll-w ${pos(k)}`}>
                  {w}
                  <em>.</em>
                </span>
              ))}
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

        <div className="device" aria-hidden="false">
          <div className="device-bar" aria-hidden="true">
            <span><i /><i /><i /></span>
            <b>HomeLedger</b>
          </div>
          <div className="device-screens">
            {screens.map((s, k) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={s} className={k === i ? "on" : ""} src={`/screens/${s}.webp`} alt={k === i ? h.chips[k] : ""} width={1280} height={800} loading={k === 0 ? "eager" : "lazy"} decoding="async" />
            ))}
          </div>
          <div className="chip" key={i} aria-hidden="true">
            <span className="chip-dot"><Icon name="check" size={12} /></span>
            {h.chips[i]}
          </div>
        </div>

        <div className="hero-stat">
          <strong>{h.stat.big}</strong>
          <span>{h.stat.text}</span>
          <small>{h.stat.note}</small>
        </div>

        <div className="hero-cards" role="tablist" aria-label="Highlights">
          {h.cards.map((c, k) => (
            <button key={c.title} type="button" role="tab" aria-selected={k === i} className={`hcard ${k === i ? "on" : ""}`} onClick={() => setI(k)}>
              <kbd className="key on-dark">{c.key}</kbd>
              <span className="hcard-t">{c.title}</span>
              <span className="hcard-s">{c.text}</span>
            </button>
          ))}
        </div>

        <a className="scroll-hint" href="#hub" aria-label={h.scroll}>
          <span>{h.scroll}</span>
          <i />
        </a>
      </div>
    </section>
  );
}
