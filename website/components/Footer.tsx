"use client";

import { useLang } from "./LanguageProvider";
import { links, site } from "@/lib/site";

export function Footer() {
  const { t } = useLang();
  const f = t.footer;
  return (
    <footer className="footer">
      <div className="container footer-in">
        <div className="footer-brand">
          <div className="brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" width={28} height={28} />
            <span>{site.name}</span>
          </div>
          <p>{f.tagline}</p>
        </div>
        <nav aria-label={f.product}>
          <h3>{f.product}</h3>
          <ul>
            <li><a href={links.repo} target="_blank" rel="noopener noreferrer">{f.source}</a></li>
            <li><a href={links.releases} target="_blank" rel="noopener noreferrer">{f.releases}</a></li>
            <li><a href={links.changelog} target="_blank" rel="noopener noreferrer">{f.changelog}</a></li>
            <li><a href={links.guideEn} target="_blank" rel="noopener">{f.guide}</a></li>
            <li><a href={links.issues} target="_blank" rel="noopener noreferrer">{f.issues}</a></li>
          </ul>
        </nav>
      </div>
      <div className="container footer-legal">
        <p>{f.rights(site.year, site.publisher)}</p>
        <p>{f.legal}</p>
      </div>
    </footer>
  );
}
