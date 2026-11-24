import type { SVGProps } from "react";

export type IconName = "offline" | "save" | "copy" | "file" | "download" | "github" | "check" | "x" | "info" | "menu" | "chevron" | "arrow";

const paths: Record<IconName, string> = {
  offline: "M2 8.8a15 15 0 0 1 4-2.6M22 8.8a15 15 0 0 0-8.5-3.7M5 12.5a10 10 0 0 1 3.2-2M19 12.5a10 10 0 0 0-4.4-2.4M8.5 16.2a5 5 0 0 1 7 0M12 20h.01M3 3l18 18",
  save: "M5 3h11l3 3v15H5zM8 3v6h7V3M8 21v-7h8v7",
  copy: "M9 9h11v11H9zM5 15V4h11",
  file: "M6 2h8l5 5v15H6zM14 2v5h5M9 13h7M9 17h7",
  download: "M12 3v12m0 0l-4.5-4.5M12 15l4.5-4.5M4 20h16",
  github:
    "M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 3 .8.1-.7.4-1.1.6-1.4-2.2-.3-4.600-1.100-4.600-5 0-1.100.4-2 1-2.700-.1-.3-.4-1.300.1-2.700 0 0 .8-.3 2.700 1a9.400 9.400 0 0 1 5 0c1.900-1.300 2.700-1 2.700-1 .5 1.400.2 2.400.1 2.700.6.7 1 1.600 1 2.700 0 3.900-2.400 4.700-4.600 5 .4.3.7.9.7 1.900v2.800c0 .3.2.6.7.5A10 10 0 0 0 12 2z",
  check: "M4 12.5l5 5L20 6.500",
  x: "M5 5l14 14M19 5L5 19",
  info: "M12 8h.01M11 12h1v5h1M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z",
  menu: "M4 6h16M4 12h16M4 18h16",
  chevron: "M6 9l6 6 6-6",
  arrow: "M7 17L17 7M8 7h9v9",
};

export function Icon({ name, size = 20, ...rest }: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  const filled = name === "github";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={paths[name]} />
    </svg>
  );
}
