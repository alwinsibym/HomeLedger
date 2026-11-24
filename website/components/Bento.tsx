"use client";

import { useEffect, useRef } from "react";
import { useLang } from "./LanguageProvider";
import { Section } from "./Section";

/** Little pictures for some tiles. They are plain HTML and SVG, so they stay sharp and cost nothing to load. */
function EntryArt() {
  return (
    <div className="art art-entry" aria-hidden="true">
      <div className="mini-row"><b>Payment</b><span>F5</span></div>
      <div className="mini-row"><span>Account</span><b>Groceries</b></div>
      <div className="mini-row"><span>Amount</span><b className="type">₹ 1,250</b></div>
      <div className="mini-row"><span>Narration</span><b>Weekly groceries</b></div>
      <div className="mini-save"><kbd className="key">Ctrl+A</kbd><span>Saved</span></div>
    </div>
  );
}

function BarsArt() {
  const v = [34, 52, 41, 68, 58, 80, 63, 92];
  return (
    <svg className="art art-bars" viewBox="0 0 160 70" preserveAspectRatio="none" aria-hidden="true">
      {v.map((h, i) => (
        <rect key={i} x={i * 20 + 4} y={70 - h * 0.7} width={12} height={h * 0.7} rx={3} style={{ ["--i" as string]: i }} />
      ))}
    </svg>
  );
}

function ChipsArt({ items }: { items: string[] }) {
  return (
    <div className="art art-chips" aria-hidden="true">
      {items.map((c) => (
        <span key={c}>{c}</span>
      ))}
    </div>
  );
}

const reports = ["Day Book", "Ledger", "Trial Balance", "Profit & Loss", "Balance Sheet"];
const files = ["bill.jpg", "rent.pdf", "bank.csv"];

export function Bento() {
  const { t } = useLang();
  const grid = useRef<HTMLDivElement>(null);

  // Tiles that scroll up past the top of the screen shrink and fade a little (--leave, 0 to 1), the mirror of the pop-in.
  useEffect(() => {
    const el = grid.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tiles = Array.from(el.children) as HTMLElement[];
    let raf = 0;
    const run = () => {
      raf = 0;
      const vh = window.innerHeight;
      for (const tile of tiles) {
        const r = tile.getBoundingClientRect();
        tile.style.setProperty("--leave", Math.min(1, Math.max(0, -r.top / (r.height + vh * 0.2))).toFixed(3));
      }
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(run); };
    run();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  const f = t.features;
  const it = f.items;
  const tile = (i: number, cls: string, art?: React.ReactNode) => (
    <article key={it[i].title} className={`tile glass rv pop ${cls}`} style={{ ["--d" as string]: `${(i % 3) * 0.09 + Math.floor(i / 3) * 0.04}s` }}>
      <kbd className="key">{it[i].key}</kbd>
      <h3>{it[i].title}</h3>
      <p>{it[i].text}</p>
      {art}
    </article>
  );
  return (
    <Section id="features" eyebrow={f.eyebrow} title={f.title} lead={f.lead}>
      <div className="bento" ref={grid}>
        {tile(0, "t-entry", <EntryArt />)}
        {tile(1, "t-dash", <BarsArt />)}
        {tile(2, "t-bill", <ChipsArt items={files} />)}
        {tile(3, "t-import")}
        {tile(4, "t-reports", <ChipsArt items={reports} />)}
        {tile(5, "t-owed")}
        {tile(6, "t-tpl")}
        {tile(7, "t-tax")}
        {tile(8, "t-safe")}
        <article className="tile dark rv pop t-off" style={{ ["--d" as string]: "0.05s" }}>
          <strong className="big-n">{t.hero.stat.big}</strong>
          <h3>{t.trust[0].title}</h3>
          <p>{t.trust[0].text}</p>
        </article>
        <article className="tile glass rv pop t-save" style={{ ["--d" as string]: "0.14s" }}>
          <h3>{t.trust[1].title}</h3>
          <p>{t.trust[1].text}</p>
        </article>
      </div>
    </Section>
  );
}
