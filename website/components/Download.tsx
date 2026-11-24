"use client";

import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { Icon } from "./Icon";
import { links } from "@/lib/site";
import type { Release } from "@/lib/release";

export function Download({ release }: { release: Release | null }) {
  const { t } = useLang();
  const d = t.download;
  const href = release?.installerUrl ?? links.releases;
  return (
    <Section id="download" eyebrow={d.eyebrow} title={d.title} lead={d.lead} tone="tint">
      <div className="dl">
        <div className="dl-main panel">
          <a className="btn primary big" href={href}>
            <Icon name="download" />
            {release?.installerUrl ? d.button : d.buttonFallback}
          </a>
          {release ? (
            <dl className="facts">
              <div><dt>{d.version}</dt><dd>{release.version}</dd></div>
              {release.sizeMb ? <div><dt>{d.size}</dt><dd>{release.sizeMb} MB</dd></div> : null}
              {release.date ? <div><dt>{d.released}</dt><dd>{release.date}</dd></div> : null}
            </dl>
          ) : null}
          <p className="small"><a href={links.changelog} target="_blank" rel="noopener noreferrer">{d.notes}</a></p>

          <h3>{d.reqTitle}</h3>
          <ul className="ticks">
            {d.req.map((r) => (
              <li key={r}><Icon name="check" size={18} /><span>{r}</span></li>
            ))}
          </ul>
        </div>

        <div className="dl-side">
          <div className="panel note">
            <h3><Icon name="info" size={20} />{d.smartTitle}</h3>
            <p>{d.smartText}</p>
          </div>
          <div className="panel">
            <h3>{d.guidesTitle}</h3>
            <ul className="linklist">
              <li><a href={links.guideEn} target="_blank" rel="noopener noreferrer">{d.guideEn}</a></li>
              <li><a href={links.guideMl} target="_blank" rel="noopener noreferrer" lang="ml">{d.guideMl}</a></li>
            </ul>
          </div>
        </div>
      </div>
    </Section>
  );
}
