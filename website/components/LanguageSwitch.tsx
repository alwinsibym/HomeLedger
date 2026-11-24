"use client";

import { useLang } from "./LanguageProvider";
import type { Lang } from "@/content/copy";

const order: Lang[] = ["en", "ml"];

export function LanguageSwitch() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="lang" role="group" aria-label={t.lang.label}>
      {order.map((l) => (
        <button key={l} type="button" className={lang === l ? "on" : ""} aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
          {t.lang[l]}
        </button>
      ))}
    </div>
  );
}
