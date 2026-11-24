"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";

export function HowItWorks() {
  const { t } = useLang();
  const h = t.how;
  return (
    <Section id="how" eyebrow={h.eyebrow} title={h.title}>
      <ol className="steps">
        {h.steps.map((s, i) => (
          <li key={s.title} className="rv" style={{ ["--d" as string]: `${i * 0.1}s` }}>
            <span className="num" aria-hidden="true">
              {i + 1}
            </span>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
