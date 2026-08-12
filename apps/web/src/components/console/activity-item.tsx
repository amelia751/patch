"use client";

import { useState } from "react";
import { ChevronRight, ChevronDown, CheckCircle2, Loader2, XCircle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ActivityData {
  id: string;
  status: "completed" | "in_progress" | "failed" | "pending";
  title: string;
  duration?: string;
  summary?: string;
  logs?: string[];
  details?: string;
}

interface ActivityItemProps {
  activity: ActivityData;
}

const statusConfig = {
  completed: {
    icon: CheckCircle2,
    color: "text-emerald-400",
  },
  in_progress: {
    icon: Loader2,
    color: "text-blue-400",
    animate: true,
  },
  failed: {
    icon: XCircle,
    color: "text-red-400",
  },
  pending: {
    icon: AlertCircle,
    color: "text-[var(--text-secondary)]",
  },
};

export function ActivityItem({ activity }: ActivityItemProps) {
  const [expanded, setExpanded] = useState(false);
  const config = statusConfig[activity.status];
  const hasDetails = activity.logs || activity.details || activity.summary;
  const Icon = config.icon;

  return (
    <div className="w-full">
      {/* Header - always visible */}
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
        className={cn(
          "w-full flex items-center gap-2 text-left py-1.5 px-2 -mx-2 rounded transition-colors",
          hasDetails && "cursor-pointer hover:bg-[var(--bg-secondary)]",
          !hasDetails && "cursor-default"
        )}
      >
        {/* Expand icon */}
        {hasDetails ? (
          expanded ? (
            <ChevronDown className="h-3 w-3 text-[var(--text-secondary)] flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-[var(--text-secondary)] flex-shrink-0" />
          )
        ) : (
          <div className="w-3" /> // Spacer when no details
        )}

        {/* Status icon */}
        <Icon className={cn(
          "h-3.5 w-3.5 flex-shrink-0",
          config.color,
          'animate' in config && config.animate && "animate-spin"
        )} />

        {/* Title */}
        <span className="text-[12px] text-[var(--text-secondary)] flex-1">
          {activity.title}
        </span>

        {/* Duration */}
        {activity.duration && (
          <span className="text-[10px] text-[var(--text-secondary)] opacity-60">
            {activity.duration}
          </span>
        )}
      </button>

      {/* Expanded content */}
      {expanded && hasDetails && (
        <div className="w-full ml-5 pl-3 border-l border-[var(--border-color)] mt-1 mb-2 pr-2">
          {/* Summary */}
          {activity.summary && (
            <p className="text-[11px] text-[var(--text-secondary)] mb-2">
              {activity.summary}
            </p>
          )}

          {/* Logs */}
          {activity.logs && activity.logs.length > 0 && (
            <div className="space-y-0.5 w-full">
              {activity.logs.map((log, idx) => (
                <div key={idx} className="text-[10px] font-mono text-[var(--text-secondary)] opacity-70 break-all">
                  {log}
                </div>
              ))}
            </div>
          )}

          {/* Details (could be code/diff in future) */}
          {activity.details && (
            <pre className="text-[10px] font-mono text-[var(--text-secondary)] bg-[var(--bg-tertiary)] p-2 rounded mt-2 overflow-x-auto w-full">
              {activity.details}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
