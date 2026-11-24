"use client";

import { useLang } from "./LanguageProvider";
import { Icon, type IconName } from "./Icon";

export function TrustStrip() {
  const { t } = useLang();
  return (
    <section className="trust" aria-label="Highlights">
      <div className="container">
        <ul className="trust-grid">
          {t.trust.map((x) => (
            <li key={x.title}>
              <span className="trust-icon">
                <Icon name={x.icon as IconName} size={22} />
              </span>
              <div>
                <strong>{x.title}</strong>
                <span>{x.text}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
