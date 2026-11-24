"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { Icon } from "./Icon";

export function Safety() {
  const { t } = useLang();
  const s = t.safety;
  const col = (c: { title: string; items: string[] }, kind: "no" | "yes") => (
    <div className={`panel panel-${kind}`}>
      <h3>{c.title}</h3>
      <ul>
        {c.items.map((x) => (
          <li key={x}>
            <Icon name={kind === "yes" ? "check" : "x"} size={18} />
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <Section id="safety" eyebrow={s.eyebrow} title={s.title} tone="tint">
      <div className="two">
        {col(s.never, "no")}
        {col(s.always, "yes")}
      </div>
    </Section>
  );
}
