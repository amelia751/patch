"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import { useTheme } from "@/lib/theme-context";
import { cn } from "@/lib/utils";
import { AddEnvironmentDialog } from "./add-environment-dialog";
import { StateSwitcher } from "./state-switcher";

interface EnvironmentConnection {
  environment: string;
  accountId: string;
  roleArn: string;
  region: string;
  connectedAt: string;
  isDefault?: boolean;
}

type DemoState = "single" | "multi-same" | "multi-different";

const DEMO_STATES: Record<DemoState, EnvironmentConnection[]> = {
  single: [
    {
      environment: "default",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
      isDefault: true,
    },
  ],
  "multi-same": [
    {
      environment: "default",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
      isDefault: true,
    },
    {
      environment: "dev",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
    },
    {
      environment: "staging",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
    },
  ],
  "multi-different": [
    {
      environment: "default",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
      isDefault: true,
    },
    {
      environment: "dev",
      accountId: "123456789012",
      roleArn: "arn:aws:iam::123456789012:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
    },
    {
      environment: "staging",
      accountId: "333333333333",
      roleArn: "arn:aws:iam::333333333333:role/DeploymentRole",
      region: "us-west-2",
      connectedAt: new Date().toISOString(),
    },
    {
      environment: "prod",
      accountId: "222222222222",
      roleArn: "arn:aws:iam::222222222222:role/DeploymentRole",
      region: "us-east-1",
      connectedAt: new Date().toISOString(),
    },
  ],
};

export function AWSConnectionUX() {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [demoState, setDemoState] = useState<DemoState>("single");
  const [connections, setConnections] = useState<EnvironmentConnection[]>(DEMO_STATES.single);
  const [expandedEnvs, setExpandedEnvs] = useState<Set<string>>(new Set());

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleStateChange = (state: DemoState) => {
    setDemoState(state);
    setConnections(DEMO_STATES[state]);
    setExpandedEnvs(new Set());
  };

  const handleAddEnvironment = (env: EnvironmentConnection) => {
    setConnections([...connections, env]);
    setShowAddDialog(false);
  };

  const handleRemoveEnvironment = (environment: string) => {
    setConnections(connections.filter((c) => c.environment !== environment));
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

  const getEnvironmentLabel = (env: string) => {
    if (env === "default") return "All Environments";
    if (env === "dev") return "Development";
    if (env === "staging") return "Staging";
    if (env === "prod") return "Production";
    return env;
  };

  const getServingText = (connection: EnvironmentConnection) => {
    if (connection.isDefault) {
      const specificEnvs = connections.filter((c) => !c.isDefault).map((c) => c.environment);
      if (specificEnvs.length === 0) {
        return "Serving: all environments";
      } else {
        const remaining = ["dev", "staging", "prod"].filter((e) => !specificEnvs.includes(e));
        if (remaining.length === 0) return "No longer serving any environment";
        return `Serving: ${remaining.join(", ")}`;
      }
    }
    return `Serving: ${connection.environment} only`;
  };

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-primary)]">
      <div className="max-w-4xl mx-auto p-6 space-y-6">
        {/* Info Banner */}
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
          <p className="text-xs text-blue-600 dark:text-blue-400">
            <strong>UX Preview:</strong> This page demonstrates the AWS multi-environment connection flow.
            Use the state switcher below to explore different user scenarios.
          </p>
        </div>

        {/* State Switcher */}
        <StateSwitcher currentState={demoState} onStateChange={handleStateChange} />

        {/* Environment Connections */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <img
                src={theme === "dark" ? "/aws-dark.svg" : "/aws-light.svg"}
                alt="AWS"
                className="h-6 w-6"
              />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">AWS Connections</h2>
            </div>
          </div>

          {/* Connection Cards */}
          <div className="space-y-3 mb-6">
            {connections.map((connection) => (
              <div
                key={connection.environment}
                className="border border-[var(--border-color)] rounded-lg overflow-hidden"
              >
                {/* Connection Header */}
                <div className="p-4 bg-[var(--bg-primary)]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" />
                        <h3 className="text-sm font-medium text-[var(--text-primary)]">
                          {getEnvironmentLabel(connection.environment)}
                        </h3>
                        {connection.isDefault && (
                          <Badge
                            variant="outline"
                            className="text-[9px] px-1.5 py-0 h-4 border-[var(--border-color)] text-[var(--text-secondary)]"
                          >
                            Default
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] mb-2">
                        Account: {connection.accountId} · Region: {connection.region}
                      </p>
                      <p className="text-[10px] text-[var(--text-secondary)] italic">
                        {getServingText(connection)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {!connection.isDefault && (
                        <button
                          onClick={() => handleRemoveEnvironment(connection.environment)}
                          className="p-1.5 rounded-md text-red-500 hover:bg-red-500/10 transition-colors border border-red-500/20"
                          title="Remove connection"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => toggleExpanded(connection.environment)}
                        className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
                        title={expandedEnvs.has(connection.environment) ? "Collapse details" : "Expand details"}
                      >
                        {expandedEnvs.has(connection.environment) ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedEnvs.has(connection.environment) && (
                  <div className="p-4 bg-[var(--bg-tertiary)] border-t border-[var(--border-color)] space-y-3">
                    <div>
                      <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">
                        IAM Role ARN
                      </label>
                      <p className="text-xs text-[var(--text-primary)] font-mono bg-[var(--bg-primary)] p-2 rounded border border-[var(--border-color)]">
                        {connection.roleArn}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">
                        Connected At
                      </label>
                      <p className="text-xs text-[var(--text-primary)]">
                        {new Date(connection.connectedAt).toLocaleString()}
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

        {/* Migration Path Explanation */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
            How the migration path works
          </h3>
          <div className="space-y-3 text-xs text-[var(--text-secondary)]">
            <div className="flex gap-3">
              <div className="h-5 w-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                1
              </div>
              <div>
                <p className="font-medium text-[var(--text-primary)] mb-1">Start with one account</p>
                <p>
                  Your initial "default" connection serves all environments (dev, staging, prod). Zero
                  complexity, just ship.
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="h-5 w-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                2
              </div>
              <div>
                <p className="font-medium text-[var(--text-primary)] mb-1">Add prod account when ready</p>
                <p>
                  Click "Add environment connection" → select "prod" → connect different AWS account. The
                  default connection automatically stops serving prod and continues serving dev & staging.
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="h-5 w-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                3
              </div>
              <div>
                <p className="font-medium text-[var(--text-primary)] mb-1">
                  Separate all environments (optional)
                </p>
                <p>
                  Add explicit connections for dev and staging too. The default connection becomes dormant
                  but stays as a fallback. No data migration needed, no downtime.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Same Account vs Different Account */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
            Same account vs different account
          </h3>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="p-4 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-lg">
              <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-2">Same Account</h4>
              <ul className="space-y-1.5 text-xs text-[var(--text-secondary)]">
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Same role ARN for all environments</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Separation via resource tagging</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Simpler setup, lower cost</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-amber-500">!</span>
                  <span>Weaker isolation (no blast radius protection)</span>
                </li>
              </ul>
            </div>
            <div className="p-4 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-lg">
              <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-2">Different Account</h4>
              <ul className="space-y-1.5 text-xs text-[var(--text-secondary)]">
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Complete account-level isolation</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Blast radius protection</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[#10b981]">✓</span>
                  <span>Better for compliance & security</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-amber-500">!</span>
                  <span>Requires AWS Organizations setup</span>
                </li>
              </ul>
            </div>
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
