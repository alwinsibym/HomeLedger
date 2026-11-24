"use client";

import { useEffect } from "react";

/**
 * One observer for the whole page. Anything with the class `rv` fades and rises into place the first time it scrolls into view.
 * Things already on screen are marked first, so nothing flashes. With "reduce motion" switched on, everything is simply shown.
 */
export function MotionRoot() {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>(".rv"));
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
      els.forEach((e) => e.classList.add("in"));
      return;
    }
    const vh = window.innerHeight;
    els.forEach((e) => {
      if (e.getBoundingClientRect().top < vh * 0.95) e.classList.add("in");
    });
    document.documentElement.classList.add("motion");
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((x) => {
          if (x.isIntersecting) {
            x.target.classList.add("in");
            io.unobserve(x.target);
          }
        }),
      { rootMargin: "0px 0px -8% 0px", threshold: 0.06 },
    );
    els.forEach((e) => {
      if (!e.classList.contains("in")) io.observe(e);
    });
    return () => io.disconnect();
  }, []);
  return null;
}
