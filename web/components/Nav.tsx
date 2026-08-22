"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Now" },
  { href: "/schedule", label: "Schedule" },
  { href: "/data", label: "Your data" },
  { href: "/method", label: "Method" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-3 px-4 sm:px-5">
        <Link href="/" className="display text-base font-bold tracking-tight text-ink sm:text-lg">
          Loadshift
        </Link>
        <nav className="flex items-center gap-0 sm:gap-1">
          {LINKS.map((l) => {
            const active = path === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`whitespace-nowrap rounded-full px-2 py-1.5 text-xs transition-colors sm:px-3 sm:text-sm ${
                  active
                    ? "bg-ink text-surface"
                    : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
