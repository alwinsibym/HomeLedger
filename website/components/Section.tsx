import type { ReactNode } from "react";

type Props = { id?: string; eyebrow?: string; title: string; lead?: string; tone?: "plain" | "tint"; children: ReactNode };

/** One consistent frame for every block of the page: a heading group, then the content. */
export function Section({ id, eyebrow, title, lead, tone = "plain", children }: Props) {
  return (
    <section id={id} className={`section section-${tone}`} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="container">
        <header className="section-head">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
          {lead ? <p className="lead">{lead}</p> : null}
        </header>
        {children}
      </div>
    </section>
  );
}
