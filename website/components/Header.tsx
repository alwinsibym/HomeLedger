"use client";

import { useEffect, useState } from "react";
import { useLang } from "./LanguageProvider";
import { LanguageSwitch } from "./LanguageSwitch";
import { Icon } from "./Icon";
import { links, site } from "@/lib/site";

const anchors = ["features", "screens", "safety", "faq"] as const;

/** Floating bar with a "notch" for the logo, like a tab cut into the top of the page. Turns light-on-dark over the hero, dark-on-light after it. */
export function Header() {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [light, setLight] = useState(false);

  useEffect(() => {
    const on = () => setLight(window.scrollY > window.innerHeight * 0.7);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  const label: Record<(typeof anchors)[number], string> = { features: t.nav.features, screens: t.nav.screens, safety: t.nav.safety, faq: t.nav.faq };
  return (
    <header className={`bar ${light ? "bar-light" : ""}`}>
      <nav className={`bar-pills ${open ? "open" : ""}`} aria-label="Main">
        {anchors.map((a) => (
          <a key={a} href={`#${a}`} onClick={() => setOpen(false)}>
            {label[a]}
          </a>
        ))}
      </nav>
      <a className="notch" href="#top" aria-label={`${site.name}, top of page`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="" width={28} height={28} />
        <span>{site.name}</span>
      </a>
      <div className="bar-end">
        <LanguageSwitch />
        <a className="pill dark" href="#download">
          {t.nav.download}
          <span className="pill-arrow"><Icon name="arrow" size={14} /></span>
        </a>
        <a className="round" href={links.repo} aria-label="GitHub" target="_blank" rel="noopener noreferrer">
          <Icon name="github" size={18} />
        </a>
        <button type="button" className="round menu-btn" aria-expanded={open} aria-label={t.nav.menu} onClick={() => setOpen((v) => !v)}>
          <Icon name={open ? "x" : "menu"} size={18} />
        </button>
      </div>
    </header>
  );
}
