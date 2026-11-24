"use client";

import { useEffect, type RefObject } from "react";

/**
 * Calls `onProgress` with a number from 0 to 1 as the element scrolls through the screen.
 * - pinned: the element is taller than the screen and holds a sticky child; 0 when its top reaches the top, 1 when its bottom reaches the bottom.
 * - otherwise: 0 when the top is at the top of the screen, 1 once the element has fully scrolled away.
 * It writes straight to the DOM through the callback, so scrolling never triggers a React re-render.
 */
export function useScrollProgress(ref: RefObject<HTMLElement | null>, onProgress: (p: number) => void, pinned = false) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onProgress(pinned ? 1 : 0);
      return;
    }
    let raf = 0;
    const run = () => {
      raf = 0;
      const r = el.getBoundingClientRect();
      const span = pinned ? r.height - window.innerHeight : r.height;
      const p = span > 0 ? -r.top / span : 0;
      onProgress(Math.min(1, Math.max(0, p)));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(run);
    };
    run();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, pinned]);
}
