import type { ReactNode } from "react";

type Props = { id?: string; eyebrow?: string; title: string; lead?: string; children: ReactNode; center?: boolean };

/** One consistent frame for every block of the page: a heading group that rises into view, then the content. */
export function Section({ id, eyebrow, title, lead, children, center = false }: Props) {
  return (
    <section id={id} className="section" aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="container">
        <header className={`section-head rv ${center ? "center" : ""}`}>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
          {lead ? <p className="lead">{lead}</p> : null}
        </header>
        {children}
      </div>
    </section>
  );
}
