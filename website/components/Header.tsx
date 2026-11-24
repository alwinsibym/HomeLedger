"use client";

import { useState } from "react";
import { useLang } from "./LanguageProvider";
import { LanguageSwitch } from "./LanguageSwitch";
import { Icon } from "./Icon";
import { links, site } from "@/lib/site";

const anchors = ["features", "screens", "how", "safety", "download", "faq"] as const;

export function Header() {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const label: Record<(typeof anchors)[number], string> = {
    features: t.nav.features,
    screens: t.nav.screens,
    how: t.nav.how,
    safety: t.nav.safety,
    download: t.nav.download,
    faq: t.nav.faq,
  };
  return (
    <header className="topbar">
      <div className="container topbar-in">
        <a className="brand" href="#top" aria-label={`${site.name}, top of page`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="" width={32} height={32} />
          <span>{site.name}</span>
        </a>
        <nav className={`nav ${open ? "open" : ""}`} aria-label="Main">
          {anchors.map((a) => (
            <a key={a} href={`#${a}`} onClick={() => setOpen(false)}>
              {label[a]}
            </a>
          ))}
        </nav>
        <div className="topbar-end">
          <LanguageSwitch />
          <a className="icon-btn" href={links.repo} aria-label="GitHub" target="_blank" rel="noopener noreferrer">
            <Icon name="github" />
          </a>
          <button type="button" className="icon-btn menu-btn" aria-expanded={open} aria-label={t.nav.menu} onClick={() => setOpen((v) => !v)}>
            <Icon name={open ? "x" : "menu"} />
          </button>
        </div>
      </div>
    </header>
  );
}
