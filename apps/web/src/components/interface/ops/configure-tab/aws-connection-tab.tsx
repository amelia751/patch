"use client";

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CheckCircle2, XCircle, Copy, Check, ChevronRight, ChevronDown, ChevronUp, Trash2, Plus } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useTheme } from "@/lib/theme-context";
import { cn } from "@/lib/utils";
import { AddEnvironmentDialog } from "@/components/interface/ux-ui/add-environment-dialog";

interface PolicyStatement {
  Effect: string;
  Action: string[];
  Resource: string | string[];
}

interface Policy {
  Version: string;
  Statement: PolicyStatement[];
}

interface RequiredPolicy {
  name: string;
  description: string;
  validated: boolean;
  policy: Policy;
}

interface EnvironmentConnection {
  environment: string;
  accountId: string;
  roleArn: string;
  region: string;
  connectedAt: string;
  isDefault?: boolean;
}

interface AWSConnectionTabProps {
  connection: {
    status: string;
    role_arn: string;
    region: string;
    account_id: string;
    connected_at: string;
    required_policies?: RequiredPolicy[];
  };
  userId?: string;
  onDisconnected?: () => void;
}

export function AWSConnectionTab({ connection, userId = "default", onDisconnected }: AWSConnectionTabProps) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [copiedPolicy, setCopiedPolicy] = useState<string | null>(null);
  const [expandedPolicy, setExpandedPolicy] = useState<string | null>(null);
  const [showDetachConfirm, setShowDetachConfirm] = useState(false);
  const [detachConfirmText, setDetachConfirmText] = useState("");
  const [isDetaching, setIsDetaching] = useState(false);
  const [detachError, setDetachError] = useState<string | null>(null);
  const [expandedEnvs, setExpandedEnvs] = useState<Set<string>>(new Set());
  const [showAddDialog, setShowAddDialog] = useState(false);

  // Hardcoded environment connections (demo data)
  const [connections, setConnections] = useState<EnvironmentConnection[]>([
    {
      environment: "default",
      accountId: connection.account_id,
      roleArn: connection.role_arn,
      region: connection.region,
      connectedAt: connection.connected_at,
      isDefault: true,
    },
  ]);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleCopyPolicy = async (policyName: string, policy: Policy) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(policy, null, 2));
      setCopiedPolicy(policyName);
      setTimeout(() => setCopiedPolicy(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleDetachConnection = async () => {
    setIsDetaching(true);
    setDetachError(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      const response = await fetch(`${API_URL}/api/aws/disconnect?user_id=${userId}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to detach AWS connection");
      }

      if (onDisconnected) {
        onDisconnected();
      } else {
        window.location.reload();
      }
    } catch (err: any) {
      console.error("Error detaching AWS connection:", err);
      setDetachError(err.message || "Failed to detach AWS connection");
    } finally {
      setIsDetaching(false);
    }
  };

  const toggleExpanded = (environment: string) => {
    const newExpanded = new Set(expandedEnvs);
    if (newExpanded.has(environment)) {
      newExpanded.delete(environment);
    } else {
      newExpanded.add(environment);
    }
    setExpandedEnvs(newExpanded);
  };

  const handleAddEnvironment = (env: EnvironmentConnection) => {
    setConnections([...connections, env]);
    setShowAddDialog(false);
  };

  const handleRemoveEnvironment = (environment: string) => {
    setConnections(connections.filter((c) => c.environment !== environment));
  };

  const getEnvironmentLabel = (env: string) => {
    if (env === "default") return "All Environments";
    if (env === "dev") return "Development";
    if (env === "staging") return "Staging";
    if (env === "prod") return "Production";
    return env;
  };

  const getServingText = (conn: EnvironmentConnection) => {
    if (conn.isDefault) {
      const specificEnvs = connections.filter((c) => !c.isDefault).map((c) => c.environment);
      if (specificEnvs.length === 0) {
        return "Serving: all environments";
      } else {
        const remaining = ["dev", "staging", "prod"].filter((e) => !specificEnvs.includes(e));
        if (remaining.length === 0) return "No longer serving any environment";
        return `Serving: ${remaining.join(", ")}`;
      }
    }
    return `Serving: ${conn.environment} only`;
  };

  const validatedCount = connection.required_policies?.filter(p => p.validated).length || 0;
  const totalCount = connection.required_policies?.length || 0;
  const allValidated = validatedCount === totalCount;

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
      <div className="p-6 space-y-6">

        {/* Environment Connections */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              {mounted && (
                <img
                  src={theme === "dark" ? "/aws-dark.svg" : "/aws-light.svg"}
                  alt="AWS"
                  className="h-6 w-6"
                />
              )}
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">AWS Connections</h2>
            </div>
          </div>

          {/* Connection Cards */}
          <div className="space-y-3 mb-6">
            {connections.map((conn) => (
              <div
                key={conn.environment}
                className="border border-[var(--border-color)] rounded-lg overflow-hidden"
              >
                {/* Connection Header */}
                <div className="p-4 bg-[var(--bg-primary)]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" />
                        <h3 className="text-sm font-medium text-[var(--text-primary)]">
                          {getEnvironmentLabel(conn.environment)}
                        </h3>
                        {conn.isDefault && (
                          <Badge
                            variant="outline"
                            className="text-[9px] px-1.5 py-0 h-4 border-[var(--border-color)] text-[var(--text-secondary)]"
                          >
                            Default
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] mb-2">
                        Account: {conn.accountId} · Region: {conn.region}
                      </p>
                      <p className="text-[10px] text-[var(--text-secondary)] italic">
                        {getServingText(conn)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {!conn.isDefault && (
                        <button
                          onClick={() => handleRemoveEnvironment(conn.environment)}
                          className="p-1.5 rounded-md text-red-500 hover:bg-red-500/10 transition-colors border border-red-500/20"
                          title="Remove connection"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => toggleExpanded(conn.environment)}
                        className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
                        title={expandedEnvs.has(conn.environment) ? "Collapse details" : "Expand details"}
                      >
                        {expandedEnvs.has(conn.environment) ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedEnvs.has(conn.environment) && (
                  <div className="p-4 bg-[var(--bg-tertiary)] border-t border-[var(--border-color)] space-y-3">
                    <div>
                      <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">
                        IAM Role ARN
                      </label>
                      <p className="text-xs text-[var(--text-primary)] font-mono bg-[var(--bg-primary)] p-2 rounded border border-[var(--border-color)] break-all">
                        {conn.roleArn}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">
                        Connected At
                      </label>
                      <p className="text-xs text-[var(--text-primary)]">
                        {new Date(conn.connectedAt).toLocaleString()}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Divider */}
          <div className="border-t border-[var(--border-color)] my-6"></div>

          {/* Environment Connections Section */}
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-primary)] mb-3">
              Environment Connections
            </h3>
            <p className="text-xs text-[var(--text-secondary)] mb-4">
              Add specific AWS account connections for different environments. Each environment can use
              the same account (logical separation via tags) or different accounts (physical isolation).
            </p>
            <Button
              onClick={() => setShowAddDialog(true)}
              variant="outline"
              className="border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
              size="sm"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add environment connection
            </Button>
          </div>
        </div>

        {/* Required Policies */}
        {connection.required_policies && connection.required_policies.length > 0 && (
          <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Required IAM Policies</h3>
              <span className="text-xs text-[var(--text-secondary)]">
                {validatedCount}/{totalCount} validated
              </span>
            </div>

            <p className="text-xs text-[var(--text-secondary)] mb-4">
              The following IAM policies must be attached to your role for full functionality.
            </p>

            <div className="space-y-3">
              {connection.required_policies.map((policy) => (
                <div
                  key={policy.name}
                  className="border border-[var(--border-color)] rounded-lg overflow-hidden"
                >
                  {/* Policy Header */}
                  <div className="p-4 bg-[var(--bg-primary)]">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {policy.validated ? (
                            <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" />
                          ) : (
                            <XCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                          )}
                          <h4 className="text-sm font-medium text-[var(--text-primary)]">{policy.name}</h4>
                        </div>
                        <p className="text-xs text-[var(--text-secondary)] ml-6">{policy.description}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleCopyPolicy(policy.name, policy.policy)}
                          className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
                          title={copiedPolicy === policy.name ? "Copied!" : "Copy policy"}
                        >
                          {copiedPolicy === policy.name ? (
                            <Check className="h-3.5 w-3.5" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => setExpandedPolicy(expandedPolicy === policy.name ? null : policy.name)}
                          className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
                        >
                          <ChevronRight
                            className={cn(
                              "h-3.5 w-3.5 transition-transform",
                              expandedPolicy === policy.name && "rotate-90"
                            )}
                          />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Policy JSON */}
                  {expandedPolicy === policy.name && (
                    <div className="p-4 bg-[var(--bg-tertiary)] border-t border-[var(--border-color)]">
                      <pre className="text-[10px] font-mono text-[var(--text-primary)] overflow-x-auto">
                        {JSON.stringify(policy.policy, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Warning if not all policies validated */}
        {!allValidated && (
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
            <p className="text-xs text-amber-600 dark:text-amber-500">
              <strong>Warning:</strong> Some required policies are missing. Deployment may fail without full permissions.
            </p>
          </div>
        )}

        {/* Danger Zone */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4 flex items-center gap-2">
            <Trash2 className="h-4 w-4" />
            Danger Zone
          </h3>

          <div className="p-5 rounded-xl border-2 border-red-500/20 bg-[var(--bg-primary)]">
            <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-2">
              Disconnect AWS Account
            </h4>
            <p className="text-[11px] text-[var(--text-secondary)] mb-4 leading-relaxed">
              Once disconnected, you will need to reconnect to AWS to deploy and manage infrastructure.
              All connection settings will be removed.
            </p>

            {!showDetachConfirm ? (
              <Button
                size="sm"
                variant="destructive"
                className="text-xs bg-red-500 hover:bg-red-600 text-white"
                onClick={() => setShowDetachConfirm(true)}
              >
                Disconnect
              </Button>
            ) : (
              <div className="space-y-3 pt-3 border-t border-red-500/20">
                <p className="text-[10px] text-[var(--text-secondary)]">
                  Type <strong className="text-red-500">DISCONNECT</strong> to confirm:
                </p>
                <Input
                  value={detachConfirmText}
                  onChange={(e) => setDetachConfirmText(e.target.value)}
                  placeholder="Type DISCONNECT to confirm"
                  className={cn(
                    "h-9 text-sm bg-[var(--bg-secondary)] text-[var(--text-primary)]",
                    detachError
                      ? "border-red-500 focus:ring-red-500"
                      : "border-red-500/30 focus:border-red-500 focus:ring-red-500/20"
                  )}
                />
                {detachError && (
                  <p className="text-[10px] text-red-500">{detachError}</p>
                )}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                    onClick={() => {
                      setShowDetachConfirm(false);
                      setDetachConfirmText("");
                      setDetachError(null);
                    }}
                    disabled={isDetaching}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    className="text-xs bg-red-500 hover:bg-red-600 text-white"
                    onClick={handleDetachConnection}
                    disabled={detachConfirmText !== "DISCONNECT" || isDetaching}
                  >
                    {isDetaching ? (
                      <>
                        <Spinner className="h-3 w-3 mr-1.5" />
                        <span className="shimmer-text">Disconnecting</span>
                      </>
                    ) : (
                      "Disconnect"
                    )}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Environment Dialog */}
      <AddEnvironmentDialog
        open={showAddDialog}
        onOpenChange={setShowAddDialog}
        onAdd={handleAddEnvironment}
        existingConnections={connections}
      />
    </div>
  );
}
