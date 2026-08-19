"use client";

import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function SectionRail({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={150}>
      <div className="w-14 md:w-56 flex-shrink-0 border-r border-[var(--border-color)] p-2 md:p-3 space-y-1">
        {children}
      </div>
    </TooltipProvider>
  );
}

export function SectionRailButton({
  active,
  icon: Icon,
  label,
  count,
  countTone = "amber",
  onClick,
}: {
  active: boolean;
  icon: LucideIcon;
  label: string;
  count?: number;
  countTone?: "amber" | "green" | "muted";
  onClick: () => void;
}) {
  const badgeClass =
    countTone === "green"
      ? "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30"
      : countTone === "muted"
        ? "text-[var(--text-secondary)] border-[var(--border-color)]"
        : "bg-amber-500/10 text-amber-500 border-amber-500/30";
  const dotClass =
    countTone === "green"
      ? "bg-[#10b981]"
      : countTone === "muted"
        ? "bg-[var(--text-secondary)]"
        : "bg-amber-500";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          className={cn(
            "relative w-full flex items-center text-xs rounded-lg transition-colors",
            "justify-center md:justify-between px-2 py-2.5 md:px-3 md:py-2",
            active
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]",
          )}
        >
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 shrink-0" />
            <span className="hidden md:inline font-medium">{label}</span>
          </div>
          {count != null && count > 0 && (
            <>
              <span
                className={cn(
                  "md:hidden absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full",
                  dotClass,
                )}
              />
              <Badge
                variant="outline"
                className={cn("hidden md:inline-flex text-[9px] h-5", badgeClass)}
              >
                {count}
              </Badge>
            </>
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" className="md:hidden">
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
