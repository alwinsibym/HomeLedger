"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { AppFrame } from "./AppFrame";

/** Tabbed screenshot gallery. Arrow keys move between tabs, as the WAI-ARIA tabs pattern expects. */
export function Screens() {
  const { t } = useLang();
  const s = t.screens;
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const n = s.tabs.length;
    let next = active;
    if (e.key === "ArrowRight") next = (active + 1) % n;
    else if (e.key === "ArrowLeft") next = (active - 1 + n) % n;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = n - 1;
    else return;
    e.preventDefault();
    setActive(next);
    refs.current[next]?.focus();
  };

  const tab = s.tabs[active];
  return (
    <Section id="screens" eyebrow={s.eyebrow} title={s.title} lead={s.lead} tone="tint">
      <div className="tabs" role="tablist" aria-label={s.title} onKeyDown={onKey}>
        {s.tabs.map((x, i) => (
          <button
            key={x.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`tab-${x.id}`}
            role="tab"
            type="button"
            aria-selected={i === active}
            aria-controls="screen-panel"
            tabIndex={i === active ? 0 : -1}
            className={i === active ? "on" : ""}
            onClick={() => setActive(i)}
          >
            {x.label}
          </button>
        ))}
      </div>
      <div id="screen-panel" role="tabpanel" aria-labelledby={`tab-${tab.id}`} className="screen-panel">
        <AppFrame src={`/screens/${tab.id}.webp`} alt={`${tab.label}: ${tab.caption}`} title={`HomeLedger · ${tab.label}`} />
        <p className="caption">{tab.caption}</p>
      </div>
    </Section>
  );
}
