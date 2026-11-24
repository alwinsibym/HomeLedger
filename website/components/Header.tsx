"use client";

import { useEffect, useRef, useState } from "react";
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

  const bar = useRef<HTMLElement>(null);
  const pills = useRef<HTMLElement>(null);

  useEffect(() => {
    // How far the link pills must slide to rest beside the (icon-only) logo. Measured again on resize.
    let shift = 0;
    const measure = () => {
      const b = bar.current, p = pills.current;
      if (!b || !p || window.innerWidth <= 860) {
        shift = 0;
        b?.style.setProperty("--shift", "0px");
        return;
      }
      const left = parseFloat(getComputedStyle(b).paddingLeft) || 26;
      const target = window.innerWidth / 2 - 32 - 36 - p.offsetWidth;
      shift = Math.max(0, target - left);
      b.style.setProperty("--shift", `${shift}px`);
    };
    let raf = 0;
    const update = () => {
      raf = 0;
      const y = window.scrollY, vh = window.innerHeight;
      const k = Math.min(1, Math.max(0, y / (vh * 0.45)));
      bar.current?.style.setProperty("--bp", k.toFixed(3));
      setLight(y > vh * 0.7);
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    const onResize = () => { measure(); onScroll(); };
    measure();
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  const label: Record<(typeof anchors)[number], string> = { features: t.nav.features, screens: t.nav.screens, safety: t.nav.safety, faq: t.nav.faq };
  return (
    <header ref={bar} className={`bar ${light ? "bar-light" : ""}`}>
      <nav ref={pills} className={`bar-pills ${open ? "open" : ""}`} aria-label="Main">
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
