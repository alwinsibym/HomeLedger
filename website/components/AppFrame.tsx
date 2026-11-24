type Props = { src: string; alt: string; title?: string; priority?: boolean };

/** A screenshot inside a simple window frame that echoes the application's own blue title bar. */
export function AppFrame({ src, alt, title = "HomeLedger", priority = false }: Props) {
  return (
    <figure className="frame">
      <div className="frame-bar" aria-hidden="true">
        <span className="frame-dots"><i /><i /><i /></span>
        <span className="frame-title">{title}</span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} width={1280} height={800} loading={priority ? "eager" : "lazy"} decoding="async" fetchPriority={priority ? "high" : "auto"} />
    </figure>
  );
}
