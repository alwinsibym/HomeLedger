"use client";

import { useRef } from "react";
import { useLang } from "./LanguageProvider";
import { useScrollProgress } from "@/hooks/useScrollProgress";

const RX = 38;
const RY = 22;

/**
 * Scroll-driven diagram. The section is tall and holds a sticky stage: as you scroll through it, the lines draw outwards
 * from the centre and each part of the program appears at the end of its line. All of it is driven by one CSS variable (--p),
 * so there is no per-frame React work. On narrow screens it becomes a plain grid.
 */
export function Hub() {
  const { t } = useLang();
  const h = t.hub;
  const ref = useRef<HTMLElement>(null);
  useScrollProgress(ref, (p) => ref.current?.style.setProperty("--p", p.toFixed(3)), true);

  const nodes = h.nodes.map((nd, i) => {
    const a = ((-90 + (360 / h.nodes.length) * i) * Math.PI) / 180;
    return { ...nd, x: 50 + RX * Math.cos(a), y: 30 + RY * Math.sin(a), s: 0.16 + i * 0.075 };
  });

  return (
    <section ref={ref} className="hub" id="hub" aria-labelledby="hub-title">
      <div className="hub-pin">
        <header className="hub-head">
          <p className="eyebrow">{h.eyebrow}</p>
          <h2 id="hub-title">{h.title}</h2>
          <p className="lead">{h.lead}</p>
        </header>
        <div className="hub-stage">
          <svg className="hub-lines" viewBox="0 0 100 60" preserveAspectRatio="none" aria-hidden="true">
            {nodes.map((n) => (
              <line key={n.t} x1={50} y1={30} x2={n.x} y2={n.y} pathLength={1} style={{ ["--s" as string]: n.s }} />
            ))}
          </svg>
          <div className="hub-core">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" width={64} height={64} />
            <span>{h.center}</span>
          </div>
          <ul className="hub-nodes">
            {nodes.map((n) => (
              <li key={n.t} className="hub-node" style={{ left: `${n.x}%`, top: `${(n.y / 60) * 100}%`, ["--s" as string]: n.s }}>
                <kbd className="key">{n.k}</kbd>
                <span>{n.t}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
