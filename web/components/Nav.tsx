"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

const LINKS = [
  { id: "now", label: "Now" },
  { id: "schedule", label: "Schedule" },
  { id: "data", label: "Your data" },
  { id: "method", label: "Method" },
];

export default function Nav() {
  const [active, setActive] = useState("now");

  // Track which section is on screen (no scroll listeners).
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: [0, 0.25, 0.5] }
    );
    LINKS.forEach((l) => {
      const el = document.getElementById(l.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-3 px-4 sm:px-5">
        <Link
          href="/#now"
          className="display text-base font-bold tracking-tight text-ink sm:text-lg"
        >
          Loadshift
        </Link>
        <nav className="flex items-center gap-0 sm:gap-1">
          {LINKS.map((l) => (
            <a
              key={l.id}
              href={`/#${l.id}`}
              className={`whitespace-nowrap rounded-full px-2 py-1.5 text-xs transition-colors sm:px-3 sm:text-sm ${
                active === l.id
                  ? "bg-ink text-surface"
                  : "text-ink-2 hover:bg-surface-2 hover:text-ink"
              }`}
            >
              {l.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}
