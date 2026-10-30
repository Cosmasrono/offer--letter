import type { ReactNode, SVGProps } from "react";

const paths = {
  shield: <><path d="m12 3 8 3.5v5c0 4.7-3.5 8-8 10-4.5-2-8-5.3-8-10v-5L12 3Z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>,
  arrow: <path d="M4 12h16M14 6l6 6-6 6" />,
  upload: <path d="M12 16V4m-4 4 4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  building: <path d="M4 21V5l8-3v19M12 8h8v13M2 21h20M8 7v1m0 3v1m0 3v1m8-4v1m0 3v1" />,
  wallet: <><path d="M20 8V5H6a3 3 0 0 0 0 6h14v9H6a3 3 0 0 1-3-3V8" /><path d="M20 12h-5v5h5M16 14.5h.01" /></>,
  warning: <path d="m10.3 4-8 14a2 2 0 0 0 1.7 3h16a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01" />,
  message: <><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0Z" /><path d="M7 10h9M7 14h6" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
} satisfies Record<string, ReactNode>;

export function Icon({ name, className = "h-5 w-5", ...props }: SVGProps<SVGSVGElement> & { name: keyof typeof paths }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} {...props}>{paths[name]}</svg>;
}
