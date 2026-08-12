"use client";

import { useState, useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Search,
  Download,
  Pause,
  Play,
  ArrowDown,
  Sparkles,
  Filter,
  X,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

// ============================================================================
// TYPES
// ============================================================================

interface LogEntry {
  id: string;
  timestamp: string;
  service: string;
  level: "debug" | "info" | "warn" | "error";
  message: string;
  trace_id?: string;
  metadata?: Record<string, string>;
}

interface LogsTabProps {
  logs: LogEntry[];
  services: string[];
}

// ============================================================================
// HELPERS
// ============================================================================

const levelConfig: Record<string, { color: string; bg: string; label: string }> = {
  debug: { color: "text-[var(--text-secondary)]", bg: "bg-[var(--bg-tertiary)]", label: "DBG" },
  info: { color: "text-blue-400", bg: "bg-blue-500/10", label: "INF" },
  warn: { color: "text-amber-400", bg: "bg-amber-500/10", label: "WRN" },
  error: { color: "text-red-400", bg: "bg-red-500/10", label: "ERR" },
};

const serviceColors: Record<string, string> = {
  "auth-service": "text-cyan-400",
  "product-service": "text-violet-400",
  "order-service": "text-orange-400",
  "payment-service": "text-emerald-400",
  "content-service": "text-pink-400",
};

function getServiceColor(service: string): string {
  return serviceColors[service] || "text-[var(--text-primary)]";
}

// ============================================================================
// COMPONENT
// ============================================================================

export function LogsTab({ logs, services }: LogsTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedService, setSelectedService] = useState<string>("all");
  const [selectedLevel, setSelectedLevel] = useState<string>("all");
  const [selectedTimeRange, setSelectedTimeRange] = useState<string>("1h");
  const [isPaused, setIsPaused] = useState(false);
  const [showAiSearch, setShowAiSearch] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Filter logs
  const filteredLogs = logs.filter((log) => {
    if (selectedService !== "all" && log.service !== selectedService) return false;
    if (selectedLevel !== "all" && log.level !== selectedLevel) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        log.message.toLowerCase().includes(q) ||
        log.service.toLowerCase().includes(q) ||
        log.trace_id?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (isAtBottom && scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLogs.length, isAtBottom, isPaused]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < 40);
  };

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      setIsAtBottom(true);
    }
  };

  const activeFilterCount = [
    selectedService !== "all",
    selectedLevel !== "all",
    searchQuery !== "",
  ].filter(Boolean).length;

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      {/* ── Toolbar ── */}
      <div className="border-b border-[var(--border-color)] px-4 py-2.5 space-y-2">
        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-secondary)]" />
            <input
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-purple-500/50"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="h-3 w-3 text-[var(--text-secondary)] hover:text-[var(--text-primary)]" />
              </button>
            )}
          </div>

          {/* Service filter */}
          <Select value={selectedService} onValueChange={setSelectedService}>
            <SelectTrigger className="w-[140px] h-7 text-[10px] bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue placeholder="All Services" />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">All Services</SelectItem>
              {services.map((s) => (
                <SelectItem key={s} value={s} className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Level filter */}
          <Select value={selectedLevel} onValueChange={setSelectedLevel}>
            <SelectTrigger className="w-[100px] h-7 text-[10px] bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue placeholder="All Levels" />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">All Levels</SelectItem>
              <SelectItem value="error" className="text-xs text-red-400 focus:bg-[var(--bg-tertiary)]">Error</SelectItem>
              <SelectItem value="warn" className="text-xs text-amber-400 focus:bg-[var(--bg-tertiary)]">Warning</SelectItem>
              <SelectItem value="info" className="text-xs text-blue-400 focus:bg-[var(--bg-tertiary)]">Info</SelectItem>
              <SelectItem value="debug" className="text-xs text-[var(--text-secondary)] focus:bg-[var(--bg-tertiary)]">Debug</SelectItem>
            </SelectContent>
          </Select>

          {/* Time range */}
          <Select value={selectedTimeRange} onValueChange={setSelectedTimeRange}>
            <SelectTrigger className="w-[90px] h-7 text-[10px] bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="15m" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Last 15m</SelectItem>
              <SelectItem value="1h" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Last 1h</SelectItem>
              <SelectItem value="6h" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Last 6h</SelectItem>
              <SelectItem value="24h" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Last 24h</SelectItem>
              <SelectItem value="7d" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Last 7d</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1 ml-auto">
            <Button
              size="sm"
              variant="ghost"
              className={cn("h-7 w-7 p-0", isPaused && "text-amber-400")}
              onClick={() => setIsPaused(!isPaused)}
            >
              {isPaused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
            </Button>
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0">
              <Download className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Active filters indicator */}
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-2">
            <Filter className="h-3 w-3 text-[var(--text-secondary)]" />
            <span className="text-[10px] text-[var(--text-secondary)]">
              {filteredLogs.length} of {logs.length} logs
            </span>
            <button
              onClick={() => { setSearchQuery(""); setSelectedService("all"); setSelectedLevel("all"); }}
              className="text-[10px] text-purple-400 hover:text-purple-300"
            >
              Clear filters
            </button>
          </div>
        )}
      </div>

      {/* ── Log Entries ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Search className="h-8 w-8 text-[var(--text-secondary)] mx-auto mb-3" />
              <p className="text-xs text-[var(--text-secondary)]">No logs match your filters</p>
            </div>
          </div>
        ) : (
          <div>
            {filteredLogs.map((log) => {
              const level = levelConfig[log.level];
              return (
                <div
                  key={log.id}
                  className={cn(
                    "flex items-start gap-0 px-4 py-1 hover:bg-[var(--bg-secondary)] transition-colors border-b border-[var(--border-color)]/30 group",
                    log.level === "error" && "bg-red-500/[0.03]"
                  )}
                >
                  {/* Timestamp */}
                  <span className="text-[var(--text-secondary)] w-[72px] shrink-0 tabular-nums select-all">
                    {new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>

                  {/* Level badge */}
                  <span className={cn("w-[36px] shrink-0 font-bold text-center", level.color)}>
                    {level.label}
                  </span>

                  {/* Service */}
                  <span className={cn("w-[130px] shrink-0 truncate px-2", getServiceColor(log.service))}>
                    {log.service}
                  </span>

                  {/* Message */}
                  <span className="text-[var(--text-primary)] flex-1 break-words">
                    {log.message}
                  </span>

                  {/* Trace ID on hover */}
                  {log.trace_id && (
                    <span className="text-[var(--text-secondary)] text-[9px] opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2">
                      {log.trace_id}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Scroll to bottom FAB ── */}
      {!isAtBottom && (
        <div className="absolute bottom-14 right-6">
          <Button
            size="sm"
            onClick={scrollToBottom}
            className="h-8 rounded-full shadow-lg bg-[var(--bg-secondary)] border border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] gap-1 text-[10px]"
          >
            <ArrowDown className="h-3 w-3" />
            New logs
          </Button>
        </div>
      )}

      {/* ── Footer ── */}
      <div className="border-t border-[var(--border-color)] px-4 py-1.5 bg-[var(--bg-secondary)] flex items-center justify-between">
        <p className="text-[10px] text-[var(--text-secondary)]">
          {filteredLogs.length} entries · {selectedTimeRange} window
          {isPaused && <span className="text-amber-400 ml-2">⏸ Paused</span>}
        </p>
        <button
          onClick={() => setShowAiSearch(!showAiSearch)}
          className="flex items-center gap-1 text-[10px] text-purple-400 hover:text-purple-300 transition-colors"
        >
          <Sparkles className="h-3 w-3" />
          AI Search
        </button>
      </div>
    </div>
  );
}
