"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  GitBranch,
  ArrowUpDown,
  RefreshCw,
  Shuffle,
  User,
  ChevronDown,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================================================
// TYPES
// ============================================================================

interface DeploymentEntry {
  id: string;
  environment: string;
  status: "success" | "failed" | "rolled_back";
  deployed_at: string;
  deployed_by: string;
  duration_seconds: number;
  version: string;
  changes?: { created: number; updated: number; deleted: number };
  error?: string;
  cost_delta?: string;
  approved_by?: string;
  initial_deployment?: boolean;
  rollback_from?: string;
}

interface DriftEvent {
  id: string;
  detected_at: string;
  resource: string;
  resource_type: string;
  drift_type: "config_change" | "missing" | "orphaned";
  detail: string;
  severity: "low" | "medium" | "high";
  auto_reconciled: boolean;
  reconciled_at?: string;
}

interface HistoryTabProps {
  deployments: DeploymentEntry[];
  driftEvents: DriftEvent[];
}

// ============================================================================
// HELPERS
// ============================================================================

const deployStatusConfig: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  success: { icon: <CheckCircle2 className="h-4 w-4" />, color: "text-emerald-400", bg: "bg-emerald-500/10" },
  failed: { icon: <XCircle className="h-4 w-4" />, color: "text-red-400", bg: "bg-red-500/10" },
  rolled_back: { icon: <RefreshCw className="h-4 w-4" />, color: "text-amber-400", bg: "bg-amber-500/10" },
};

const driftSeverityConfig: Record<string, { color: string; bg: string; border: string }> = {
  low: { color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  medium: { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  high: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20" },
};

const driftTypeLabel: Record<string, string> = {
  config_change: "Config Changed",
  missing: "Resource Missing",
  orphaned: "Orphaned Resource",
};

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return minutes > 0 ? `${minutes}m ${secs}s` : `${secs}s`;
}

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  return "just now";
}

// ============================================================================
// COMPONENT
// ============================================================================

export function HistoryTab({ deployments, driftEvents }: HistoryTabProps) {
  const [activeView, setActiveView] = useState<"deployments" | "drift">("deployments");
  const [expandedDeploy, setExpandedDeploy] = useState<string | null>(deployments[0]?.id || null);

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      {/* ── View Switcher ── */}
      <div className="border-b border-[var(--border-color)] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveView("deployments")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
              activeView === "deployments"
                ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            )}
          >
            <span className="flex items-center gap-1.5">
              <GitBranch className="h-3 w-3" />
              Deployments
              <Badge variant="outline" className="text-[8px] ml-0.5 px-1.5 py-0 border-[var(--border-color)] text-[var(--text-secondary)]">
                {deployments.length}
              </Badge>
            </span>
          </button>
          <button
            onClick={() => setActiveView("drift")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
              activeView === "drift"
                ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            )}
          >
            <span className="flex items-center gap-1.5">
              <Shuffle className="h-3 w-3" />
              Drift Events
              {driftEvents.filter((d) => !d.auto_reconciled).length > 0 && (
                <Badge variant="outline" className="text-[8px] ml-0.5 px-1.5 py-0 bg-amber-500/10 text-amber-400 border-amber-500/20">
                  {driftEvents.filter((d) => !d.auto_reconciled).length}
                </Badge>
              )}
            </span>
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto">
        {/* Deployments View */}
        {activeView === "deployments" && (
          <div className="max-w-4xl mx-auto p-6">
            {/* Timeline */}
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-[19px] top-0 bottom-0 w-px bg-[var(--border-color)]" />

              <div className="space-y-1">
                {deployments.map((deploy, idx) => {
                  const config = deployStatusConfig[deploy.status];
                  const isExpanded = expandedDeploy === deploy.id;
                  return (
                    <div key={deploy.id} className="relative">
                      <button
                        onClick={() => setExpandedDeploy(isExpanded ? null : deploy.id)}
                        className="w-full text-left"
                      >
                        <div className="flex items-start gap-4 pl-0 py-3 hover:bg-[var(--bg-secondary)] rounded-lg px-2 transition-colors">
                          {/* Timeline dot */}
                          <div className={cn("relative z-10 p-1.5 rounded-full shrink-0", config.bg, config.color)}>
                            {config.icon}
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-xs font-medium text-[var(--text-primary)]">
                                {deploy.initial_deployment ? "Initial deployment" : `Deploy ${deploy.version}`} → {deploy.environment}
                              </span>
                              {deploy.initial_deployment && (
                                <Badge variant="outline" className="text-[8px] bg-blue-500/10 text-blue-400 border-blue-500/20">
                                  Initial
                                </Badge>
                              )}
                              {deploy.rollback_from && (
                                <Badge variant="outline" className="text-[8px] bg-amber-500/10 text-amber-400 border-amber-500/20">
                                  Rollback from {deploy.rollback_from}
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-3 text-[10px] text-[var(--text-secondary)]">
                              <span className="flex items-center gap-1">
                                <User className="h-3 w-3" />
                                {deploy.deployed_by}
                              </span>
                              <span>{relativeTime(deploy.deployed_at)}</span>
                              <span>{formatDuration(deploy.duration_seconds)}</span>
                            </div>
                          </div>

                          {/* Expand indicator */}
                          {isExpanded ? <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] shrink-0 mt-0.5" /> : <ChevronRight className="h-4 w-4 text-[var(--text-secondary)] shrink-0 mt-0.5" />}
                        </div>
                      </button>

                      {/* Expanded details */}
                      {isExpanded && (
                        <div className="ml-[52px] mb-3 pl-4 border-l-2 border-[var(--border-color)]">
                          <div className="bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)] p-4 space-y-3">
                            {/* Changes */}
                            {deploy.status === "success" && deploy.changes && (
                              <div className="flex items-center gap-4 text-[10px]">
                                <span className="text-[var(--text-secondary)]">Changes:</span>
                                {deploy.changes.created > 0 && <span className="text-emerald-400">+{deploy.changes.created} created</span>}
                                {deploy.changes.updated > 0 && <span className="text-amber-400">~{deploy.changes.updated} updated</span>}
                                {deploy.changes.deleted > 0 && <span className="text-red-400">-{deploy.changes.deleted} deleted</span>}
                              </div>
                            )}

                            {/* Error */}
                            {deploy.status === "failed" && deploy.error && (
                              <div className="bg-red-500/5 border border-red-500/20 rounded-md px-3 py-2">
                                <p className="text-[10px] text-red-400">{deploy.error}</p>
                              </div>
                            )}

                            {/* Metadata */}
                            <div className="flex items-center gap-4 text-[10px] text-[var(--text-secondary)]">
                              <span>
                                {new Date(deploy.deployed_at).toLocaleString([], {
                                  month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit"
                                })}
                              </span>
                              {deploy.cost_delta && (
                                <span className="text-emerald-400">{deploy.cost_delta}</span>
                              )}
                              {deploy.approved_by && (
                                <span>Approved by {deploy.approved_by}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Drift Events View */}
        {activeView === "drift" && (
          <div className="max-w-4xl mx-auto p-6 space-y-3">
            {driftEvents.length === 0 ? (
              <div className="flex items-center justify-center py-20">
                <div className="text-center">
                  <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto mb-3" />
                  <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">No drift detected</h3>
                  <p className="text-xs text-[var(--text-secondary)]">All resources match their expected configuration.</p>
                </div>
              </div>
            ) : (
              driftEvents.map((event) => {
                const severity = driftSeverityConfig[event.severity];
                return (
                  <div
                    key={event.id}
                    className={cn(
                      "rounded-lg border p-4",
                      severity.bg, severity.border
                    )}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <ArrowUpDown className={cn("h-4 w-4", severity.color)} />
                        <span className="text-xs font-medium text-[var(--text-primary)]">{event.resource}</span>
                        <Badge variant="outline" className={cn("text-[8px]", severity.color, severity.border)}>
                          {driftTypeLabel[event.drift_type]}
                        </Badge>
                      </div>
                      {event.auto_reconciled ? (
                        <Badge variant="outline" className="text-[8px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20 gap-1">
                          <CheckCircle2 className="h-2.5 w-2.5" />
                          Auto-reconciled
                        </Badge>
                      ) : (
                        <Button size="sm" className="h-6 text-[10px] bg-purple-500 hover:bg-purple-600 text-white gap-1">
                          <Sparkles className="h-3 w-3" />
                          Reconcile
                        </Button>
                      )}
                    </div>
                    <p className="text-[11px] text-[var(--text-primary)] ml-6 mb-2">{event.detail}</p>
                    <div className="flex items-center gap-3 ml-6 text-[10px] text-[var(--text-secondary)]">
                      <span>{event.resource_type}</span>
                      <span>Detected {relativeTime(event.detected_at)}</span>
                      {event.reconciled_at && <span>Reconciled {relativeTime(event.reconciled_at)}</span>}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
