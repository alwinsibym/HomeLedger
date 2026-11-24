"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";

export function Shortcuts() {
  const { t } = useLang();
  const k = t.keys;
  return (
    <Section id="keys" eyebrow={k.eyebrow} title={k.title} lead={k.lead}>
      <dl className="keys">
        {k.rows.map(([key, what]) => (
          <div key={key} className="keyrow glass rv">
            <dt>
              <kbd className="key">{key}</kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}
