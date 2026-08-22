"use client";
import { useEffect, useState } from "react";

/** Wake/bed hours (local, 0-23), persisted per browser. */
export function useWakeBed(): [number, number, (w: number, b: number) => void] {
  const [wake, setWake] = useState(7);
  const [bed, setBed] = useState(23);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("loadshift.wakebed");
      if (raw) {
        const [w, b] = JSON.parse(raw);
        if (Number.isInteger(w) && Number.isInteger(b)) {
          setWake(w);
          setBed(b);
        }
      }
    } catch {
      /* storage unavailable: defaults stand */
    }
  }, []);

  const update = (w: number, b: number) => {
    setWake(w);
    setBed(b);
    try {
      localStorage.setItem("loadshift.wakebed", JSON.stringify([w, b]));
    } catch {
      /* fine */
    }
  };
  return [wake, bed, update];
}

/** Is local hour h inside the awake window [wake, bed)? Handles wraparound. */
export const isAwake = (h: number, wake: number, bed: number) =>
  wake < bed ? h >= wake && h < bed : h >= wake || h < bed;
