/** Soft colour that drifts slowly behind the whole page, so the glass cards have something to blur. */
export function PageGlow() {
  return (
    <div className="glow" aria-hidden="true">
      <i className="g1" />
      <i className="g2" />
      <i className="g3" />
    </div>
  );
}
