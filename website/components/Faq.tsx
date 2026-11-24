"use client";

import { useState } from "react";
import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { Icon } from "./Icon";

/** One answer open at a time. The reveal class sits on a wrapper React never re-renders with a new class name, so the "in" mark survives. Each answer slides open with a height animation that needs no measuring (grid rows 0fr to 1fr). */
export function Faq() {
  const { t } = useLang();
  const f = t.faq;
  const [open, setOpen] = useState<number | null>(0);
  return (
    <Section id="faq" eyebrow={f.eyebrow} title={f.title}>
      <div className="faq">
        {f.items.map((it, i) => {
          const isOpen = open === i;
          return (
            <div key={it.q} className="rv" style={{ ["--d" as string]: `${i * 0.05}s` }}>
            <div className={`faq-item glass ${isOpen ? "open" : ""}`}>
              <h3>
                <button type="button" id={`faq-q-${i}`} aria-expanded={isOpen} aria-controls={`faq-a-${i}`} onClick={() => setOpen(isOpen ? null : i)}>
                  <span>{it.q}</span>
                  <span className="faq-icon"><Icon name="chevron" size={18} /></span>
                </button>
              </h3>
              <div id={`faq-a-${i}`} role="region" aria-labelledby={`faq-q-${i}`} className="faq-a">
                <div>
                  <p>{it.a}</p>
                </div>
              </div>
            </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}
