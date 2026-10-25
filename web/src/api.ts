import { useCallback, useEffect, useState } from "react";
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string" ? data.detail : "请检查输入内容。";
    } catch {
      /* HTTP error can have an empty body */
    }
    throw new Error(message);
  }
  return response.json();
}
export function useApi<T>(path: string | null, interval = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(Boolean(path));
  const refresh = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    setLoading(Boolean(path));
    if (!path) return;
    const read = async () => {
      try {
        const value = await api<T>(path);
        if (active) {
          setData(value);
          setError("");
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "请求失败");
      } finally {
        if (active) setLoading(false);
      }
    };
    void read();
    const id = interval
      ? window.setInterval(() => {
          if (!document.hidden) void read();
        }, interval)
      : undefined;
    return () => {
      active = false;
      if (id) window.clearInterval(id);
    };
  }, [path, interval]);
  return { data, error, loading, refresh };
}
export const number = (value: number | undefined) =>
  value === undefined ? "—" : new Intl.NumberFormat("zh-CN").format(value);
export const date = (value: number) =>
  new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
export const colors = [
  "#08b590",
  "#428dfb",
  "#e6ab37",
  "#ed6980",
  "#a180ed",
  "#31b7ca",
  "#f28b4e",
  "#94b348",
];
