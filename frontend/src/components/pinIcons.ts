import type { Facility } from "../types";

const OPEN =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';

export function pinIconSvg(f: Facility): string {
  if (f.type === "hospital") return `${OPEN}<path d="M12 5v14M5 12h14"/></svg>`;
  if (f.type === "clinic")
    return `${OPEN}<circle cx="12" cy="12" r="8.5"/><path d="M12 8v8M8 12h8"/></svg>`;
  if (f.center_type === "temporary")
    return `${OPEN}<path d="M12 4L3.5 19h17L12 4z"/><path d="M9.8 19l2.2-4.5 2.2 4.5"/></svg>`;
  return `${OPEN}<path d="M3.5 11L12 4l8.5 7"/><path d="M6 10v10h12V10"/></svg>`;
}