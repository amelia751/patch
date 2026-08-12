"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, GitPullRequestArrow, Radio, ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * The four operational views of roadmap §17. Deliberately not a chat surface:
 * PatchAPI is watched, not conversed with.
 */
const NAV = [
  { title: "Changes", href: "/", icon: Radio, match: (p: string) => p === "/" },
  {
    title: "Organization impact",
    href: "/impact",
    icon: Building2,
    match: (p: string) => p.startsWith("/impact"),
  },
  {
    title: "Runs",
    href: "/runs",
    icon: GitPullRequestArrow,
    match: (p: string) => p.startsWith("/runs"),
  },
  {
    title: "Fleet & governance",
    href: "/fleet",
    icon: ShieldCheck,
    match: (p: string) => p.startsWith("/fleet"),
  },
] as const;

export function Sidebar() {
  const pathname = usePathname() ?? "/";

  return (
    <aside className="flex w-16 shrink-0 flex-col border-r border-border bg-[var(--surface-secondary)]">
      <div className="border-b border-border px-2 py-3">
        <Link href="/" aria-label="Patch — changes">
          <div className="flex items-center justify-center rounded-md bg-primary p-2.5 text-primary-foreground transition-all duration-200 hover:bg-primary-hover active:scale-95">
            <PatchMark className="size-5" />
          </div>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-3">
        <TooltipProvider delayDuration={100}>
          {NAV.map((item) => {
            const active = item.match(pathname);
            const Icon = item.icon;
            return (
              <Tooltip key={item.href}>
                <TooltipTrigger asChild>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group flex items-center justify-center rounded-md p-3 transition-colors duration-200",
                      active
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-[var(--surface-tertiary)] hover:text-foreground",
                    )}
                  >
                    <Icon className="size-5 transition-transform duration-200 group-hover:scale-110" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">{item.title}</TooltipContent>
              </Tooltip>
            );
          })}
        </TooltipProvider>
      </nav>
    </aside>
  );
}

/** The Patch mark: a diff hunk closing up. */
function PatchMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M4 7h7M4 12h5M4 17h7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M16 5v14M20 12l-4 4-4-4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
