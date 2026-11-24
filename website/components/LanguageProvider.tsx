"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { copy, type Copy, type Lang } from "@/content/copy";

type Ctx = { lang: Lang; t: Copy; setLang: (l: Lang) => void };

const LanguageContext = createContext<Ctx | null>(null);
const KEY = "hl_site_lang";

export function LanguageProvider({ children }: { children: ReactNode }) {
  // Always start in English so the server and the first browser render match; then apply a saved choice.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === "ml" || saved === "en") setLangState(saved);
    } catch {
      /* storage blocked: stay in English */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ lang, t: copy[lang], setLang }), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang(): Ctx {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used inside <LanguageProvider>");
  return ctx;
}
