"use client";

import { Terminal, FileCode, Logs, Bell, BellOff, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ActionBarProps {
  showLogs?: boolean;
  notificationsEnabled?: boolean;
  onToggleLogs?: () => void;
  onToggleNotifications?: () => void;
  onViewConsole?: () => void;
  onViewCode?: () => void;
}

export function ActionBar({
  showLogs = false,
  notificationsEnabled = true,
  onToggleLogs,
  onToggleNotifications,
  onViewConsole,
  onViewCode,
}: ActionBarProps) {
  return (
    <div className="border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2">
      <div className="flex items-center justify-between">
        {/* Left Actions */}
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleLogs}
            className={cn(
              "h-7 px-2 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              showLogs && "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
            )}
          >
            <Logs className="h-3 w-3 mr-1" />
            Logs
          </Button>
          
          <Button
            variant="ghost"
            size="sm"
            onClick={onViewConsole}
            className="h-7 px-2 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <Terminal className="h-3 w-3 mr-1" />
            Console
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onViewCode}
            className="h-7 px-2 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <FileCode className="h-3 w-3 mr-1" />
            Code
          </Button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleNotifications}
            className={cn(
              "h-7 px-2 text-[11px]",
              notificationsEnabled 
                ? "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]" 
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            )}
          >
            {notificationsEnabled ? (
              <>
                <Bell className="h-3 w-3 mr-1" />
                Notifications on
              </>
            ) : (
              <>
                <BellOff className="h-3 w-3 mr-1" />
                Notifications off
              </>
            )}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <ExternalLink className="h-3 w-3 mr-1" />
            AWS Console
          </Button>
        </div>
      </div>
    </div>
  );
}
