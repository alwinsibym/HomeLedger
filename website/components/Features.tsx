"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";

export function Features() {
  const { t } = useLang();
  const f = t.features;
  return (
    <Section id="features" eyebrow={f.eyebrow} title={f.title} lead={f.lead}>
      <ul className="cards">
        {f.items.map((it) => (
          <li key={it.title} className="card">
            <kbd className="key">{it.key}</kbd>
            <h3>{it.title}</h3>
            <p>{it.text}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
