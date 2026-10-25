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
export const compact = (value: number | undefined) =>
  value === undefined
    ? "—"
    : new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
export const percent = (value: number | undefined, digits = 0) =>
  value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
export const ago = (value: number) => {
  const seconds = Math.max(0, Date.now() / 1000 - value);
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return date(value);
};
export const avatarUrl = (id: string, version?: number) =>
  `/api/avatars/${id}${version === undefined ? "" : `?v=${version}`}`;
