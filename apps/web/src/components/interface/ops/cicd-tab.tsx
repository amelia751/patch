"use client";

import { useState, useEffect, useCallback } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Rocket,
  Shield,
  GitBranch,
  GitPullRequest,
  RefreshCw,
  Play,
  Ban,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Copy,
  Check,
  ClipboardClock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// TYPES
// =============================================================================

interface DeploymentRecord {
  id: string;
  project_id: string;
  trigger: string;
  triggered_by?: string;
  environment: string;
  commit_sha?: string;
  branch?: string;
  pr_number?: number;
  status: string;
  workflow_id?: string;
  thread_id?: string;
  api_endpoint?: string;
  deployed_resources?: Record<string, string>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

interface PolicyRule {
  id?: string;
  environment: string;
  branch_patterns: string[];
  auto_deploy: boolean;
  require_approval: boolean;
  pr_action: string;
}

interface PipelineMockData {
  latestByEnv: Record<string, DeploymentRecord | null>;
  deployments: DeploymentRecord[];
  policies: PolicyRule[];
  usingDefaults: boolean;
}

interface CiCdTabProps {
  projectId?: string;
  hasProject?: boolean;
  mockData?: PipelineMockData;
}

// =============================================================================
// HELPERS
// =============================================================================

function relativeTime(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function statusColor(status: string): string {
  switch (status) {
    case "succeeded":
      return "text-emerald-500";
    case "failed":
      return "text-red-500";
    case "deploying":
    case "analyzing":
      return "text-zinc-500";
    case "pending":
    case "approval_required":
      return "text-amber-500";
    case "cancelled":
      return "text-zinc-500";
    default:
      return "text-zinc-400";
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "succeeded":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "deploying":
    case "analyzing":
      return <Loader2 className="h-4 w-4 text-zinc-500 animate-spin" />;
    case "pending":
      return <Clock className="h-4 w-4 text-amber-500" />;
    case "approval_required":
      return <ClipboardClock className="h-4 w-4 text-amber-500" />;
    case "cancelled":
      return <Ban className="h-4 w-4 text-zinc-500" />;
    default:
      return <Clock className="h-4 w-4 text-zinc-400" />;
  }
}

function envBadgeColor(env: string): string {
  switch (env) {
    case "dev":
      return "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30";
    case "staging":
      return "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30";
    case "prod":
      return "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30";
    default:
      return "bg-zinc-500/20 text-zinc-600 dark:text-zinc-400 border-zinc-500/30";
  }
}

function triggerLabel(trigger: string): string {
  switch (trigger) {
    case "push":
      return "Git Push";
    case "pr_merge":
      return "PR Merge";
    case "manual":
      return "Manual";
    case "promotion":
      return "Promotion";
    case "rollback":
      return "Rollback";
    default:
      return trigger;
  }
}

// =============================================================================
// CONFIRMATION MODAL
// =============================================================================

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText: string;
  confirmIcon?: React.ReactNode;
  variant?: "default" | "warning" | "danger";
}

function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText,
  confirmIcon,
  variant = "default",
}: ConfirmationModalProps) {
  if (!isOpen) return null;

  const variantStyles = {
    default: "bg-primary hover:bg-primary/90 text-primary-foreground",
    warning: "bg-amber-500 hover:bg-amber-500/90 text-white",
    danger: "bg-red-500 hover:bg-red-500/90 text-white",
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6 max-w-md w-full mx-4">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          {title}
        </h3>
        <p className="text-xs text-[var(--text-secondary)] mb-4" dangerouslySetInnerHTML={{ __html: description }} />
        <div className="flex items-center gap-2 justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={onClose}
            className="h-8 text-xs bg-transparent border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={onConfirm}
            className={cn("h-8 text-xs", variantStyles[variant])}
          >
            {confirmIcon}
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// ENVIRONMENT CARD
// =============================================================================

function EnvironmentCard({
  env,
  deployment,
  policy,
  onDeploy,
  onApprove,
}: {
  env: string;
  deployment?: DeploymentRecord | null;
  policy?: PolicyRule;
  onDeploy?: (env: string) => void;
  onApprove?: (deploymentId: string) => void;
}) {
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [copiedError, setCopiedError] = useState(false);
  const envLabel = env === "dev" ? "Development" : env === "staging" ? "Staging" : "Production";
  const isActive = deployment && ["deploying", "analyzing", "pending"].includes(deployment.status);

  const handleCopyError = () => {
    navigator.clipboard.writeText(deployment?.error_message || '');
    setCopiedError(true);
    setTimeout(() => setCopiedError(false), 2000);
  };

  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)] p-4 hover:border-[var(--text-secondary)]/30 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={cn("text-[10px] font-bold uppercase px-2", envBadgeColor(env))}>
            {env}
          </Badge>
          <span className="text-xs text-[var(--text-secondary)]">{envLabel}</span>
        </div>
        {deployment && statusIcon(deployment.status)}
      </div>

      {/* Latest deployment info */}
      {deployment ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span className={cn("font-medium capitalize", statusColor(deployment.status))}>
              {deployment.status.replace("_", " ")}
            </span>
            {deployment.created_at && (
              <span
                className="text-[var(--text-secondary)] cursor-help"
                title={new Date(deployment.created_at).toLocaleString()}
              >
                {relativeTime(deployment.created_at)}
              </span>
            )}
          </div>

          {deployment.commit_sha && (
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
              <GitBranch className="h-3 w-3" />
              <span className="font-mono">{deployment.commit_sha.slice(0, 7)}</span>
              {deployment.branch && (
                <>
                  <span className="text-[var(--text-secondary)]/50">on</span>
                  <span className="font-medium text-[var(--text-primary)]">{deployment.branch}</span>
                </>
              )}
            </div>
          )}

          {deployment.api_endpoint && (
            <a
              href={deployment.api_endpoint}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[11px] text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              {deployment.api_endpoint.replace(/^https?:\/\//, "").slice(0, 40)}
            </a>
          )}

          {deployment.triggered_by && (
            <div className="text-[10px] text-[var(--text-secondary)]">
              {triggerLabel(deployment.trigger)} by {deployment.triggered_by}
            </div>
          )}

          {/* Error message for failed deployments - Vercel-style expandable */}
          {deployment.status === "failed" && deployment.error_message && (
            <div className="mt-2">
              <button
                onClick={() => setShowErrorDetails(!showErrorDetails)}
                className="w-full flex items-center justify-between p-2 bg-red-500/10 border border-red-500/30 rounded-md hover:bg-red-500/15 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                  <span className="text-[11px] text-red-400 font-medium">
                    Build failed
                  </span>
                </div>
                {showErrorDetails ? (
                  <ChevronUp className="h-3.5 w-3.5 text-red-400" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 text-red-400" />
                )}
              </button>

              {showErrorDetails && (
                <div className="mt-1 p-3 bg-[var(--bg-primary)] border border-red-500/30 rounded-md">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-medium text-red-400 uppercase tracking-wider">Error Details</span>
                    <button
                      onClick={handleCopyError}
                      className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                    >
                      {copiedError ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    </button>
                  </div>
                  <pre className="text-[10px] text-[var(--text-secondary)] font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-48 overflow-y-auto">
                    {deployment.error_message}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          {deployment.status === "approval_required" && onApprove && (
            <button
              onClick={() => onApprove(deployment.id)}
              className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium bg-amber-500/15 text-amber-400 rounded-md hover:bg-amber-500/25 transition-colors"
            >
              <ClipboardClock className="h-3 w-3" />
              Approve Deploy
            </button>
          )}

          {/* Retry button for failed deployments */}
          {deployment.status === "failed" && onDeploy && (
            <button
              onClick={() => onDeploy(env)}
              className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium bg-red-500/15 text-red-400 rounded-md hover:bg-red-500/25 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              Retry Deployment
            </button>
          )}
        </div>
      ) : (
        <div className="text-xs text-[var(--text-secondary)] italic">No deployments yet</div>
      )}

      {/* Deploy button - now more prominent */}
      {!isActive && onDeploy && (
        <button
          onClick={() => onDeploy(env)}
          className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Play className="h-3 w-3" />
          Deploy to {env === "dev" ? "Development" : env === "staging" ? "Staging" : "Production"}
        </button>
      )}
    </div>
  );
}

// =============================================================================
// DEPLOYMENT ROW
// =============================================================================

function DeploymentRow({ deployment }: { deployment: DeploymentRecord }) {
  const [showError, setShowError] = useState(false);
  const [copiedLog, setCopiedLog] = useState(false);
  const hasError = deployment.status === "failed" && deployment.error_message;

  const handleCopyLog = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(deployment.error_message || '');
    setCopiedLog(true);
    setTimeout(() => setCopiedLog(false), 2000);
  };

  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)] overflow-hidden">
      <div className={cn(
        "flex items-center gap-3 px-4 py-3 transition-colors",
        hasError && "cursor-pointer hover:bg-[var(--bg-tertiary)]"
      )} onClick={() => hasError && setShowError(!showError)}>
        {statusIcon(deployment.status)}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn("text-[9px] font-bold uppercase", envBadgeColor(deployment.environment))}>
              {deployment.environment}
            </Badge>
            <span className={cn("text-xs font-medium capitalize", statusColor(deployment.status))}>
              {deployment.status.replace("_", " ")}
            </span>
            {deployment.commit_sha && (
              <span className="text-[10px] font-mono text-[var(--text-secondary)]">
                {deployment.commit_sha.slice(0, 7)}
              </span>
            )}
            {deployment.branch && (
              <span className="text-[10px] text-[var(--text-secondary)]">
                on <span className="font-medium">{deployment.branch}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[var(--text-secondary)]">
            <span>{triggerLabel(deployment.trigger)}</span>
            {deployment.triggered_by && (
              <>
                <span>•</span>
                <span>{deployment.triggered_by}</span>
              </>
            )}
            {deployment.created_at && (
              <>
                <span>•</span>
                <span
                  className="cursor-help"
                  title={new Date(deployment.created_at).toLocaleString()}
                >
                  {relativeTime(deployment.created_at)}
                </span>
              </>
            )}
          </div>
        </div>

        {deployment.api_endpoint && (
          <a
            href={deployment.api_endpoint}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-primary hover:underline flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}

        {hasError && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-red-400 font-medium">
              Build failed
            </span>
            {showError ? (
              <ChevronUp className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
            )}
          </div>
        )}
      </div>

      {/* Expandable error details */}
      {hasError && showError && (
        <div className="px-4 pb-3 pt-0">
          <div className="p-3 bg-[var(--bg-primary)] border border-red-500/30 rounded-md">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-medium text-red-400 uppercase tracking-wider">Build Logs</span>
              <button
                onClick={handleCopyLog}
                className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                {copiedLog ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              </button>
            </div>
            <pre className="text-[10px] text-[var(--text-secondary)] font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
              {deployment.error_message}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function CiCdTab({ projectId, hasProject = true, mockData }: CiCdTabProps) {
  const isDemo = !!mockData;

  const [latestByEnv, setLatestByEnv] = useState<Record<string, DeploymentRecord | null>>({});
  const [deployments, setDeployments] = useState<DeploymentRecord[]>([]);
  const [policies, setPolicies] = useState<PolicyRule[]>([]);
  const [usingDefaults, setUsingDefaults] = useState(true);
  const [isLoading, setIsLoading] = useState(!isDemo);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    type: "deploy" | "approve";
    env?: string;
    deploymentId?: string;
  } | null>(null);

  // Load mock data when in demo mode
  useEffect(() => {
    if (mockData) {
      setLatestByEnv(mockData.latestByEnv || {});
      setDeployments(mockData.deployments || []);
      setPolicies(mockData.policies || []);
      setUsingDefaults(mockData.usingDefaults ?? false);
      setIsLoading(false);
    }
  }, [mockData]);

  const fetchData = useCallback(async () => {
    if (isDemo || !projectId) return;

    try {
      const [latestRes, historyRes, policyRes] = await Promise.all([
        fetch(`${API_URL}/api/projects/${projectId}/deployments/latest/by-environment`, {
          credentials: "include",
        }),
        fetch(`${API_URL}/api/projects/${projectId}/deployments?page_size=20`, {
          credentials: "include",
        }),
        fetch(`${API_URL}/api/projects/${projectId}/policies`, {
          credentials: "include",
        }),
      ]);

      if (latestRes.ok) {
        setLatestByEnv(await latestRes.json());
      }
      if (historyRes.ok) {
        const data = await historyRes.json();
        setDeployments(data.deployments || []);
      }
      if (policyRes.ok) {
        const data = await policyRes.json();
        setPolicies(data.policies || []);
        setUsingDefaults(data.using_defaults ?? true);
      }
    } catch (err) {
      console.error("Failed to fetch pipeline data:", err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [projectId, isDemo]);

  useEffect(() => {
    if (isDemo) return; // Skip fetching in demo mode
    if (hasProject && projectId) {
      fetchData();
    } else {
      setIsLoading(false);
    }
  }, [hasProject, projectId, fetchData, isDemo]);

  // Auto-refresh every 10s when there's an active deployment (skip in demo)
  useEffect(() => {
    if (isDemo) return;
    const hasActive = deployments.some((d) =>
      ["pending", "deploying", "analyzing", "approval_required"].includes(d.status)
    );
    if (!hasActive) return;

    const interval = setInterval(() => fetchData(), 10000);
    return () => clearInterval(interval);
  }, [deployments, fetchData, isDemo]);

  // Listen for deployment_status SSE events for instant refresh
  useEffect(() => {
    if (isDemo || !projectId) return;

    const url = `${API_URL}/api/projects/${projectId}/stream`;
    let es: EventSource | null = null;
    let timeoutId: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        es = new EventSource(url, { withCredentials: true });
        es.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data);
            if (event.type === "deployment_status") {
              fetchData();
            }
          } catch { /* ignore parse errors */ }
        };
        es.onerror = () => {
          es?.close();
          es = null;
          timeoutId = setTimeout(connect, 30000);
        };
      } catch { /* ignore connection errors */ }
    };

    connect();
    return () => {
      es?.close();
      clearTimeout(timeoutId);
    };
  }, [isDemo, projectId, fetchData]);

  const handleRefresh = () => {
    if (isDemo) return;
    setIsRefreshing(true);
    fetchData();
  };

  const handleDeployClick = (env: string) => {
    setConfirmAction({ type: "deploy", env });
  };

  const handleApproveClick = (deploymentId: string) => {
    setConfirmAction({ type: "approve", deploymentId });
  };

  const performDeploy = async (env: string) => {
    if (isDemo || !projectId) return;

    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/deployments`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment: env,
          user_id: "current-user", // TODO: Get from auth context
        }),
      });

      if (res.ok) {
        fetchData();
      }
    } catch (err) {
      console.error("Failed to trigger deployment:", err);
    } finally {
      setConfirmAction(null);
    }
  };

  const performApprove = async (deploymentId: string) => {
    if (isDemo || !projectId) return;

    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/deployments/${deploymentId}/approve`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approver: "current-user" }),
        }
      );

      if (res.ok) {
        fetchData();
      }
    } catch (err) {
      console.error("Failed to approve deployment:", err);
    } finally {
      setConfirmAction(null);
    }
  };

  const handleConfirm = () => {
    if (!confirmAction) return;

    if (confirmAction.type === "deploy" && confirmAction.env) {
      performDeploy(confirmAction.env);
    } else if (confirmAction.type === "approve" && confirmAction.deploymentId) {
      performApprove(confirmAction.deploymentId);
    }
  };

  // Empty state
  if (!hasProject) {
    return (
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center max-w-md">
          <Rocket className="h-12 w-12 text-[var(--text-secondary)] mx-auto mb-4 opacity-40" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">No project selected</h3>
          <p className="text-xs text-[var(--text-secondary)]">
            Select a project to view its CI/CD pipeline and deployment history.
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <Loader2 className="h-6 w-6 text-[var(--text-secondary)] animate-spin" />
      </div>
    );
  }

  // Policy lookup for environment cards
  const policyByEnv = policies.reduce<Record<string, PolicyRule>>((acc, p) => {
    acc[p.environment] = p;
    return acc;
  }, {});

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-primary)]">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">CI/CD Pipeline</h2>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              GitHub-native deploy pipeline • Branch → Environment routing
            </p>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)] disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
          </button>
        </div>

        {/* Environment Cards */}
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
            Environments
          </h3>
          <div className="grid grid-cols-3 gap-4">
            {["dev", "staging", "prod"].map((env) => (
              <EnvironmentCard
                key={env}
                env={env}
                deployment={latestByEnv[env]}
                policy={policyByEnv[env]}
                onDeploy={handleDeployClick}
                onApprove={handleApproveClick}
              />
            ))}
          </div>
        </div>

        {/* Policy Summary */}
        <div className="bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
              Branch Routing Policy
            </h3>
            {usingDefaults && (
              <Badge variant="outline" className="text-[9px] h-5 bg-blue-500/10 text-blue-400 border-blue-500/30">
                defaults
              </Badge>
            )}
          </div>
          <div className="space-y-2">
            {policies.map((policy, idx) => (
              <div key={idx} className="flex items-center gap-3 text-xs">
                <Badge variant="outline" className={cn("text-[9px] w-16 justify-center", envBadgeColor(policy.environment))}>
                  {policy.environment}
                </Badge>
                <div className="flex items-center gap-1.5 text-[var(--text-secondary)]">
                  <GitBranch className="h-3 w-3" />
                  <div className="flex items-center gap-1 flex-wrap">
                    {policy.branch_patterns.map((pattern, idx) => (
                      <span
                        key={idx}
                        className="font-mono text-[10px] text-[var(--text-primary)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 rounded border border-[var(--border-color)]"
                      >
                        {pattern}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 ml-auto text-[10px]">
                  {policy.auto_deploy && (
                    <span className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-color)]">
                      auto-deploy
                    </span>
                  )}
                  {policy.require_approval && (
                    <span className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-color)]">
                      approval
                    </span>
                  )}
                  {policy.pr_action && (
                    <span className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-color)]">
                      on PR: {policy.pr_action}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Deployment History */}
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
            Deployment History
          </h3>
          {deployments.length > 0 ? (
            <div className="space-y-2">
              {deployments.map((d) => (
                <DeploymentRow key={d.id} deployment={d} />
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <GitPullRequest className="h-10 w-10 mx-auto mb-4 text-[var(--text-secondary)] opacity-40" />
              <p className="text-sm font-medium text-[var(--text-primary)] mb-1">No deployments yet</p>
              <p className="text-xs text-[var(--text-secondary)] mb-4">
                Deploy your first environment to get started
              </p>
              <div className="flex items-center justify-center gap-2">
                {["dev", "staging", "prod"].map((env) => (
                  <button
                    key={env}
                    onClick={() => handleDeployClick(env)}
                    className="px-3 py-1.5 text-[11px] font-medium bg-[var(--bg-secondary)] text-[var(--text-primary)] rounded-md hover:bg-[var(--bg-tertiary)] border border-[var(--border-color)] transition-colors"
                  >
                    Deploy {env}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Confirmation Modal */}
        <ConfirmationModal
          isOpen={!!confirmAction}
          onClose={() => setConfirmAction(null)}
          onConfirm={handleConfirm}
          title={
            confirmAction?.type === "deploy"
              ? "Confirm Deployment"
              : "Confirm Approval"
          }
          description={
            confirmAction?.type === "deploy"
              ? `Are you sure you want to deploy to <strong>${confirmAction.env === "dev" ? "Development" : confirmAction.env === "staging" ? "Staging" : "Production"}</strong>? This will trigger a new deployment.`
              : "Are you sure you want to approve this deployment? It will proceed immediately after approval."
          }
          confirmText={
            confirmAction?.type === "deploy" ? "Deploy Now" : "Approve"
          }
          confirmIcon={
            confirmAction?.type === "deploy" ? (
              <Play className="h-3 w-3 mr-1" />
            ) : (
              <ClipboardClock className="h-3 w-3 mr-1" />
            )
          }
          variant={
            confirmAction?.env === "prod" ? "danger" : "default"
          }
        />
      </div>
    </div>
  );
}
