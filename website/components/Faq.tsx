"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { Icon } from "./Icon";

/** Uses native <details>, so it works with the keyboard and screen readers with no extra script. */
export function Faq() {
  const { t } = useLang();
  const f = t.faq;
  return (
    <Section id="faq" eyebrow={f.eyebrow} title={f.title}>
      <div className="faq">
        {f.items.map((it) => (
          <details key={it.q} className="glass rv">
            <summary>
              <span>{it.q}</span>
              <Icon name="chevron" size={18} />
            </summary>
            <p>{it.a}</p>
          </details>
        ))}
      </div>
    </Section>
  );
}
