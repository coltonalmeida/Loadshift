"use client";
import { useEffect, useState } from "react";

const STORAGE_KEY = "loadshift.geminikey";

/**
 * An optional user-supplied Gemini key, persisted in this browser only.
 * It is sent as a header on our two insight requests and is never stored
 * server-side. The shared key stays in the server environment and never
 * reaches the browser at all.
 */
export function useGeminiKey(): [string, (k: string) => void] {
  const [key, setKey] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setKey(raw);
    } catch {
      /* storage unavailable: no saved key */
    }
  }, []);

  const update = (k: string) => {
    const trimmed = k.trim();
    setKey(trimmed);
    try {
      if (trimmed) localStorage.setItem(STORAGE_KEY, trimmed);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* fine */
    }
  };
  return [key, update];
}
