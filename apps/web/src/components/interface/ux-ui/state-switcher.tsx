"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StateSwitcherProps {
  currentState: "single" | "multi-same" | "multi-different";
  onStateChange: (state: "single" | "multi-same" | "multi-different") => void;
}

export function StateSwitcher({ currentState, onStateChange }: StateSwitcherProps) {
  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-4">
      <h3 className="text-xs font-semibold text-[var(--text-primary)] mb-3">
        Demo States (for testing UX)
      </h3>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={currentState === "single" ? "default" : "outline"}
          onClick={() => onStateChange("single")}
          className={cn(
            "text-xs transition-colors",
            currentState === "single"
              ? "bg-primary hover:bg-primary/90 text-primary-foreground"
              : "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          )}
        >
          Single Connection
          <Badge variant="outline" className={cn(
            "ml-2 text-[9px] px-1.5 py-0 h-4",
            currentState === "single"
              ? "border-white/30 text-white"
              : "border-[var(--border-color)] text-[var(--text-secondary)]"
          )}>
            Bucket A
          </Badge>
        </Button>
        <Button
          size="sm"
          variant={currentState === "multi-same" ? "default" : "outline"}
          onClick={() => onStateChange("multi-same")}
          className={cn(
            "text-xs transition-colors",
            currentState === "multi-same"
              ? "bg-primary hover:bg-primary/90 text-primary-foreground"
              : "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          )}
        >
          Multi-Env (Same Account)
          <Badge variant="outline" className={cn(
            "ml-2 text-[9px] px-1.5 py-0 h-4",
            currentState === "multi-same"
              ? "border-white/30 text-white"
              : "border-[var(--border-color)] text-[var(--text-secondary)]"
          )}>
            Bucket B
          </Badge>
        </Button>
        <Button
          size="sm"
          variant={currentState === "multi-different" ? "default" : "outline"}
          onClick={() => onStateChange("multi-different")}
          className={cn(
            "text-xs transition-colors",
            currentState === "multi-different"
              ? "bg-primary hover:bg-primary/90 text-primary-foreground"
              : "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          )}
        >
          Multi-Env (Different Accounts)
          <Badge variant="outline" className={cn(
            "ml-2 text-[9px] px-1.5 py-0 h-4",
            currentState === "multi-different"
              ? "border-white/30 text-white"
              : "border-[var(--border-color)] text-[var(--text-secondary)]"
          )}>
            Bucket C
          </Badge>
        </Button>
      </div>
      <p className="text-[10px] text-[var(--text-secondary)] mt-2">
        Switch between states to see how the UX adapts for different user scenarios
      </p>
    </div>
  );
}
