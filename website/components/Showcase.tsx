"use client";

import { useEffect, useRef, useState } from "react";
import { useLang } from "./LanguageProvider";
import { Section } from "./Section";
import { AppFrame } from "./AppFrame";

/**
 * Scroll-told screenshots. On a wide screen the window stays pinned while the captions scroll past, and the picture changes
 * with the caption that is in the middle of the screen. On a phone each caption simply carries its own picture.
 */
export function Showcase() {
  const { t } = useLang();
  const s = t.screens;
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.i));
        });
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [s.tabs.length]);

  return (
    <Section id="screens" eyebrow={s.eyebrow} title={s.title} lead={s.lead}>
      <div className="show">
        <ol className="show-steps">
          {s.tabs.map((x, i) => (
            <li
              key={x.id}
              data-i={i}
              ref={(el) => {
                refs.current[i] = el;
              }}
              className={i === active ? "on" : ""}
            >
              <span className="show-n">{String(i + 1).padStart(2, "0")}</span>
              <h3>{x.label}</h3>
              <p>{x.caption}</p>
              <div className="show-inline">
                <AppFrame src={`/screens/${x.id}.webp`} alt={`${x.label}: ${x.caption}`} title={`HomeLedger · ${x.label}`} />
              </div>
            </li>
          ))}
        </ol>
        <div className="show-pin" aria-hidden="true">
          <div className="show-frame glass">
            <div className="frame-bar">
              <span className="frame-dots"><i /><i /><i /></span>
              <span className="frame-title">HomeLedger · {s.tabs[active].label}</span>
            </div>
            <div className="show-imgs">
              {s.tabs.map((x, i) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={x.id} src={`/screens/${x.id}.webp`} alt="" width={1280} height={800} loading="lazy" decoding="async" className={i === active ? "on" : ""} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </Section>
  );
}
