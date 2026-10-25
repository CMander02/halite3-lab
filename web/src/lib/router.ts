import { useEffect, useState } from "react";

// Minimal pushState router: internal <a href="/..."> links navigate without reloads.
const listeners = new Set<() => void>();

export function navigate(to: string, replace = false) {
  if (to === location.pathname + location.search) return;
  if (replace) history.replaceState(null, "", to);
  else history.pushState(null, "", to);
  window.scrollTo(0, 0);
  listeners.forEach((fn) => fn());
}

export function useLocation() {
  const [, force] = useState(0);
  useEffect(() => {
    const update = () => force((n) => n + 1);
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return { path: location.pathname.replace(/\/$/, "") || "/", search: new URLSearchParams(location.search) };
}

export function interceptLinks() {
  const handler = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = (event.target as HTMLElement | null)?.closest("a");
    if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin || url.pathname.startsWith("/api/") || /\.\w+$/.test(url.pathname)) return;
    event.preventDefault();
    navigate(url.pathname + url.search);
  };
  document.addEventListener("click", handler);
  return () => document.removeEventListener("click", handler);
}
