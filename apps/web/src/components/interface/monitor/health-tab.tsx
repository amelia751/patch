"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Lock,
  Activity,
  Clock,
  DollarSign,
  Database,
  HardDrive,
  Sparkles,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Wrench,
  ScrollText,
  Zap,
  TrendingUp,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================================================
// TYPES
// ============================================================================

interface Service {
  name: string;
  type: string;
  status: "healthy" | "warning" | "error";
  requests_24h: number;
  errors_24h: number;
  avg_duration_ms: number;
  memory_mb: number;
  error_rate?: number;
}

interface DatabaseResource {
  name: string;
  type: string;
  status: "healthy" | "warning" | "error";
  connections: number;
  max_connections: number;
  storage_gb: number;
  cpu_percent: number;
}

interface StorageResource {
  name: string;
  type: string;
  objects: number;
  size_gb: number;
}

interface AIInsight {
  id: string;
  severity: "critical" | "warning" | "info";
  service: string;
  environment: string;
  title: string;
  ai_diagnosis: string;
  suggested_action: string;
  timestamp: string;
}

interface EnvironmentHealth {
  status: "healthy" | "degraded" | "error" | "not_deployed";
  services_count: number;
  alerts_count: number;
  endpoint_url?: string;
  last_deployed?: string;
  monthly_cost?: number;
  services?: Service[];
  databases?: DatabaseResource[];
  storage?: StorageResource[];
}

interface HealthTabProps {
  environments: Record<string, EnvironmentHealth>;
  insights: AIInsight[];
  currentEnvironment: string;
  onEnvironmentChange: (env: string) => void;
}

// ============================================================================
// STATUS HELPERS
// ============================================================================

const envStatusConfig: Record<string, { color: string; bg: string; border: string; icon: React.ReactNode; label: string }> = {
  healthy: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", icon: <CheckCircle2 className="h-5 w-5" />, label: "Healthy" },
  degraded: { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20", icon: <AlertTriangle className="h-5 w-5" />, label: "Degraded" },
  error: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20", icon: <XCircle className="h-5 w-5" />, label: "Error" },
  not_deployed: { color: "text-[var(--text-secondary)]", bg: "bg-[var(--bg-secondary)]", border: "border-[var(--border-color)]", icon: <Lock className="h-5 w-5" />, label: "Not Deployed" },
};

const serviceStatusDot: Record<string, string> = {
  healthy: "bg-emerald-400",
  warning: "bg-amber-400",
  error: "bg-red-400",
};

const insightSeverityConfig: Record<string, { bg: string; border: string; icon: React.ReactNode; dot: string }> = {
  critical: { bg: "bg-red-500/5", border: "border-red-500/20", icon: <XCircle className="h-4 w-4 text-red-400" />, dot: "bg-red-400" },
  warning: { bg: "bg-amber-500/5", border: "border-amber-500/20", icon: <AlertTriangle className="h-4 w-4 text-amber-400" />, dot: "bg-amber-400" },
  info: { bg: "bg-blue-500/5", border: "border-blue-500/20", icon: <Activity className="h-4 w-4 text-blue-400" />, dot: "bg-blue-400" },
};

// ============================================================================
// COMPONENT
// ============================================================================

export function HealthTab({ environments, insights, currentEnvironment, onEnvironmentChange }: HealthTabProps) {
  const [expandedInsight, setExpandedInsight] = useState<string | null>(insights[0]?.id || null);

  const envData = environments[currentEnvironment];
  const envConfig = envStatusConfig[envData?.status || "not_deployed"];

  // Get insights for current environment
  const currentInsights = insights.filter((i) => i.environment === currentEnvironment);

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-primary)]">
      <div className="max-w-5xl mx-auto p-6 space-y-5">

        {/* ── Environment Cards ── */}
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(environments).map(([env, data]) => {
            const config = envStatusConfig[data.status];
            const isActive = env === currentEnvironment;
            return (
              <button
                key={env}
                onClick={() => onEnvironmentChange(env)}
                className={cn(
                  "relative rounded-lg border p-4 text-left transition-all",
                  isActive
                    ? `${config.bg} ${config.border} ring-1 ring-offset-0 ring-[var(--border-color)]`
                    : "bg-[var(--bg-secondary)] border-[var(--border-color)] hover:border-[var(--text-secondary)]/30"
                )}
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-[var(--text-primary)] capitalize">{env}</span>
                  <span className={cn("flex items-center gap-1", config.color)}>
                    {config.icon}
                  </span>
                </div>
                <div className="space-y-1">
                  <p className={cn("text-[10px] font-medium", config.color)}>{config.label}</p>
                  {data.status !== "not_deployed" ? (
                    <div className="flex items-center gap-3 text-[10px] text-[var(--text-secondary)]">
                      <span>{data.services_count} services</span>
                      {data.alerts_count > 0 && (
                        <span className="text-amber-400">{data.alerts_count} alert{data.alerts_count > 1 ? "s" : ""}</span>
                      )}
                    </div>
                  ) : (
                    <p className="text-[10px] text-[var(--text-secondary)]">Requires setup</p>
                  )}
                </div>
                {isActive && (
                  <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-[var(--text-primary)]" />
                )}
              </button>
            );
          })}
        </div>

        {/* ── Environment header ── */}
        {envData && envData.status !== "not_deployed" && (
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-[var(--text-primary)] capitalize">
                  {currentEnvironment}
                </h2>
                <Badge variant="outline" className={cn("text-[9px] gap-1", envConfig.bg, envConfig.color, envConfig.border)}>
                  {envConfig.icon}
                  <span className="ml-0.5">{envConfig.label}</span>
                </Badge>
              </div>
              {envData.endpoint_url && (
                <a href={envData.endpoint_url} target="_blank" rel="noopener noreferrer"
                  className="text-[11px] text-blue-400 hover:underline flex items-center gap-1 mt-1">
                  {envData.endpoint_url}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <div className="flex items-center gap-4 text-[10px] text-[var(--text-secondary)]">
              {envData.last_deployed && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {new Date(envData.last_deployed).toLocaleDateString('en-US', { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </span>
              )}
              {envData.monthly_cost !== undefined && (
                <span className="flex items-center gap-1 text-emerald-400">
                  <DollarSign className="h-3 w-3" />
                  ${envData.monthly_cost.toFixed(2)}/mo
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── AI Insights ── */}
        {currentInsights.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-4 w-4 text-purple-400" />
              <h3 className="text-xs font-semibold text-[var(--text-primary)]">AI Insights</h3>
              <Badge variant="outline" className="text-[9px] bg-purple-500/10 text-purple-400 border-purple-500/20">
                {currentInsights.length}
              </Badge>
            </div>
            <div className="space-y-2">
              {currentInsights.map((insight) => {
                const config = insightSeverityConfig[insight.severity];
                const isExpanded = expandedInsight === insight.id;
                return (
                  <div
                    key={insight.id}
                    className={cn(
                      "rounded-lg border transition-all",
                      config.bg, config.border
                    )}
                  >
                    <button
                      onClick={() => setExpandedInsight(isExpanded ? null : insight.id)}
                      className="w-full px-4 py-3 flex items-start gap-3 text-left"
                    >
                      {config.icon}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-[var(--text-primary)]">{insight.title}</span>
                          <Badge variant="outline" className="text-[8px] text-[var(--text-secondary)] border-[var(--border-color)]">
                            {insight.service}
                          </Badge>
                        </div>
                        <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">
                          {new Date(insight.timestamp).toLocaleString('en-US', { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </p>
                      </div>
                      {isExpanded ? <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] shrink-0" /> : <ChevronRight className="h-4 w-4 text-[var(--text-secondary)] shrink-0" />}
                    </button>

                    {isExpanded && (
                      <div className="px-4 pb-4 pt-0">
                        <div className="ml-7 pl-4 border-l-2 border-purple-500/20">
                          <div className="flex items-start gap-2 mb-3">
                            <Sparkles className="h-3 w-3 text-purple-400 mt-0.5 shrink-0" />
                            <p className="text-[11px] text-[var(--text-primary)] leading-relaxed">
                              {insight.ai_diagnosis}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button size="sm" className="h-6 text-[10px] bg-purple-500 hover:bg-purple-600 text-white gap-1">
                              <Wrench className="h-3 w-3" />
                              {insight.suggested_action}
                            </Button>
                            <Button size="sm" variant="ghost" className="h-6 text-[10px] text-[var(--text-secondary)] gap-1">
                              <ScrollText className="h-3 w-3" />
                              View Logs
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Quick Stats ── */}
        {envData && envData.status !== "not_deployed" && envData.services && (
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-1.5">
                <Activity className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                <span className="text-[9px] text-[var(--text-secondary)]">24h</span>
              </div>
              <p className="text-lg font-bold text-[var(--text-primary)]">
                {envData.services.reduce((sum, s) => sum + s.requests_24h, 0).toLocaleString()}
              </p>
              <p className="text-[9px] text-[var(--text-secondary)]">Requests</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-1.5">
                <XCircle className="h-3.5 w-3.5 text-red-400" />
                <span className="text-[9px] text-[var(--text-secondary)]">24h</span>
              </div>
              <p className="text-lg font-bold text-[var(--text-primary)]">
                {envData.services.reduce((sum, s) => sum + s.errors_24h, 0)}
              </p>
              <p className="text-[9px] text-[var(--text-secondary)]">Errors</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-1.5">
                <Clock className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                <span className="text-[9px] text-[var(--text-secondary)]">avg</span>
              </div>
              <p className="text-lg font-bold text-[var(--text-primary)]">
                {Math.round(envData.services.reduce((sum, s) => sum + s.avg_duration_ms, 0) / envData.services.length)}
                <span className="text-xs font-normal text-[var(--text-secondary)]">ms</span>
              </p>
              <p className="text-[9px] text-[var(--text-secondary)]">Latency</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-1.5">
                <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-[9px] text-[var(--text-secondary)]">24h</span>
              </div>
              <p className="text-lg font-bold text-[var(--text-primary)]">
                {(100 - (envData.services.reduce((sum, s) => sum + s.errors_24h, 0) / Math.max(envData.services.reduce((sum, s) => sum + s.requests_24h, 0), 1) * 100)).toFixed(1)}
                <span className="text-xs font-normal text-[var(--text-secondary)]">%</span>
              </p>
              <p className="text-[9px] text-[var(--text-secondary)]">Uptime</p>
            </div>
          </div>
        )}

        {/* ── Services ── */}
        {envData && envData.services && envData.services.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-2">
              <Zap className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
              Services
            </h3>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg overflow-hidden">
              <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-x-6 px-4 py-2 border-b border-[var(--border-color)] text-[9px] text-[var(--text-secondary)] uppercase tracking-wider font-medium">
                <span />
                <span>Service</span>
                <span className="text-right">Requests</span>
                <span className="text-right">Errors</span>
                <span className="text-right">Latency</span>
                <span className="text-right">Error Rate</span>
              </div>
              <div className="divide-y divide-[var(--border-color)]">
                {envData.services.map((service) => {
                  const errorRate = service.requests_24h > 0
                    ? (service.errors_24h / service.requests_24h * 100)
                    : 0;
                  return (
                    <div key={service.name} className="grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-x-6 items-center px-4 py-3 hover:bg-[var(--bg-tertiary)] transition-colors">
                      <div className={cn("w-2 h-2 rounded-full", serviceStatusDot[service.status])} />
                      <div>
                        <p className="text-xs font-medium text-[var(--text-primary)]">{service.name}</p>
                        <p className="text-[9px] text-[var(--text-secondary)]">{service.type} · {service.memory_mb}MB</p>
                      </div>
                      <p className="text-xs text-[var(--text-primary)] text-right tabular-nums">{service.requests_24h.toLocaleString()}</p>
                      <p className={cn("text-xs text-right tabular-nums", service.errors_24h > 0 ? "text-red-400" : "text-[var(--text-primary)]")}>
                        {service.errors_24h}
                      </p>
                      <p className="text-xs text-[var(--text-primary)] text-right tabular-nums">{service.avg_duration_ms}ms</p>
                      <div className="flex items-center justify-end gap-1.5">
                        <div className="w-12 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              errorRate > 5 ? "bg-red-400" : errorRate > 1 ? "bg-amber-400" : "bg-emerald-400"
                            )}
                            style={{ width: `${Math.min(errorRate * 10, 100)}%` }}
                          />
                        </div>
                        <span className={cn(
                          "text-[10px] tabular-nums w-8 text-right",
                          errorRate > 5 ? "text-red-400" : errorRate > 1 ? "text-amber-400" : "text-[var(--text-secondary)]"
                        )}>
                          {errorRate.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ── Databases ── */}
        {envData && envData.databases && envData.databases.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-2">
              <Database className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
              Databases
            </h3>
            <div className="grid grid-cols-1 gap-3">
              {envData.databases.map((db) => (
                <div key={db.name} className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={cn("w-2 h-2 rounded-full", serviceStatusDot[db.status])} />
                      <span className="text-xs font-medium text-[var(--text-primary)]">{db.name}</span>
                      <Badge variant="outline" className="text-[8px] text-[var(--text-secondary)] border-[var(--border-color)]">{db.type}</Badge>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-[9px] text-[var(--text-secondary)] mb-1">Connections</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full", db.connections / db.max_connections > 0.8 ? "bg-red-400" : "bg-emerald-400")}
                            style={{ width: `${(db.connections / db.max_connections) * 100}%` }}
                          />
                        </div>
                        <span className="text-[10px] text-[var(--text-primary)] tabular-nums">{db.connections}/{db.max_connections}</span>
                      </div>
                    </div>
                    <div>
                      <p className="text-[9px] text-[var(--text-secondary)] mb-1">Storage</p>
                      <p className="text-xs font-medium text-[var(--text-primary)]">{db.storage_gb}GB</p>
                    </div>
                    <div>
                      <p className="text-[9px] text-[var(--text-secondary)] mb-1">CPU</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full", db.cpu_percent > 80 ? "bg-red-400" : db.cpu_percent > 50 ? "bg-amber-400" : "bg-emerald-400")}
                            style={{ width: `${db.cpu_percent}%` }}
                          />
                        </div>
                        <span className="text-[10px] text-[var(--text-primary)] tabular-nums">{db.cpu_percent}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Storage ── */}
        {envData && envData.storage && envData.storage.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-2">
              <HardDrive className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
              Storage
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {envData.storage.map((bucket) => (
                <div key={bucket.name} className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-medium text-[var(--text-primary)]">{bucket.name}</p>
                    <p className="text-[9px] text-[var(--text-secondary)]">{bucket.type}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-[var(--text-primary)] tabular-nums">{bucket.objects.toLocaleString()} objects</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">{bucket.size_gb}GB</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Not Deployed state ── */}
        {envData && envData.status === "not_deployed" && (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="w-14 h-14 rounded-full bg-[var(--bg-secondary)] flex items-center justify-center mx-auto mb-4">
                <Lock className="h-6 w-6 text-[var(--text-secondary)]" />
              </div>
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Production not deployed</h3>
              <p className="text-xs text-[var(--text-secondary)] max-w-xs mb-4">
                Deploy to production to see live health metrics and AI insights.
              </p>
              <Button size="sm" className="h-8 text-xs bg-purple-500 hover:bg-purple-600 text-white gap-1">
                <ArrowRight className="h-3 w-3" />
                Deploy to Production
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
