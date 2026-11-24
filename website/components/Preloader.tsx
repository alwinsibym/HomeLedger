"use client";

import { useEffect, useState } from "react";

const MIN_MS = 1400;
const MAX_MS = 3200;

/**
 * Opening screen. It is part of the server-rendered page, so it covers the site from the very first paint.
 * It shows the logo and a progress line for at least 1.4 s (and until the page has loaded, never longer than 3.2 s),
 * then lifts away while the hero zooms out into place. Without JavaScript, or with "reduce motion", it simply disappears.
 */
export function Preloader() {
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState<"on" | "leaving" | "gone">("on");

  useEffect(() => {
    const root = document.documentElement;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setPhase("gone");
      return;
    }
    root.classList.add("pre");
    let loaded = document.readyState === "complete";
    const onLoad = () => (loaded = true);
    window.addEventListener("load", onLoad);
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const el = now - t0;
      const target = Math.min(el / MIN_MS, 1) * 90 + (loaded ? 10 : 0);
      setPct((v) => Math.max(v, Math.min(100, Math.round(target))));
      if ((el >= MIN_MS && loaded) || el >= MAX_MS) {
        setPct(100);
        setPhase("leaving");
        root.classList.remove("pre");
        root.classList.add("ready");
        window.setTimeout(() => setPhase("gone"), 1200);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("load", onLoad);
    };
  }, []);

  if (phase === "gone") return null;
  return (
    <div className={`preloader ${phase === "leaving" ? "leaving" : ""}`} role="status" aria-live="polite" aria-label="Loading HomeLedger">
      <div className="pl-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="" width={84} height={84} />
        <span className="pl-name">HomeLedger</span>
        <span className="pl-bar"><i style={{ transform: `scaleX(${pct / 100})` }} /></span>
        <span className="pl-num">{pct}</span>
      </div>
    </div>
  );
}
