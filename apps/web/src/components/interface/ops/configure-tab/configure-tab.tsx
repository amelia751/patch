"use client";

import { useEffect, useState } from "react";
import { Cloud, Fingerprint, Key, Vault } from "lucide-react";
import { SectionRail, SectionRailButton } from "@/components/interface/shared/section-rail";
// import { AuthTab } from "./auth-tab";
import { AWSConnectEmptyState } from "./aws-connect-empty-state";
import { AWSConnectionTab } from "./aws-connection-tab";
import { GCPConnectEmptyState } from "./gcp-connect-empty-state";
import { GCPConnectionTab, type GcpStoredConnection } from "./gcp-connection-tab";
import { SecretsTab, type WorkspaceRef } from "./secrets-tab";
import type { SecretRepoOption } from "@/components/interface/secret-managers";
import { AgentIdentityTab } from "./agent-identity-tab";
import { AuthManagerTab } from "./auth-manager-tab";
import {
  AuthManagerEmptyState,
  ChooseCloudProviderEmptyState,
  ConnectionEmptyState,
  IdentityEmptyState,
  SecretsEmptyState,
} from "./section-empty-states";

type ConfigureSection = "connection" | "secrets" | "identity" | "auth_manager";

function isResolvedCloudProvider(p: string | null | undefined): p is "aws" | "gcp" {
  return p === "aws" || p === "gcp";
}

interface RequiredPolicy {
  name: string;
  description: string;
  validated: boolean;
  policy: any;
}

interface ConfigureTabProps {
  connection: {
    status: string;
    role_arn?: string;
    account_id?: string;
    required_policies?: RequiredPolicy[];
    project_id?: string;
    project_number?: string;
    service_account_email?: string;
    required_apis?: any[];
    region: string;
    connected_at: string;
  };
  environmentConnections?: {
    dev?: any;
    staging?: any;
    prod?: any;
  };
  gcpConnections?: GcpStoredConnection[];
  secrets: {
    configured: any[];
    pending: any[];
  };
  userId?: string;
  cloudProvider?: string | null;
  hasProject?: boolean;
  projectId?: string;
  /** Workspaces from project settings (demo uses mock-ops.workspaces). */
  workspaces?: WorkspaceRef[];
  repoFullName?: string | null;
  repoDefaultBranch?: string | null;
  repos?: SecretRepoOption[];
  /** Demo / logged-out: secrets UI uses mock data and Add simulates save. */
  secretsPreviewMode?: boolean;
  /** Logged-in: showing demo-shaped data until the API returns real secrets — hide destructive/example actions that would hit the API with fake ids. */
  secretsUseMockFallback?: boolean;
  /** False while AWS/GCP account is not linked — Connection shows inline connect flow instead of the connected dashboard. */
  cloudAccountConnected?: boolean;
  onCloudConnect?: () => void;
  awsConnectExternalId?: string;
  /** Shown on GCP connect empty state (e.g. pick another provider). */
  onChooseAnotherCloudProvider?: () => void;
  onRequirementSatisfied?: () => void;
  /** When set, shown for projects with no cloud_provider (null/unknown) on the Connection section */
  onChooseCloudProvider?: () => void;
  onCloudDisconnected?: () => void;
  /** Deep-link from e.g. /?configureSection=auth or /ops?configureSection=auth */
  initialSection?: "connection" | "secrets" | "auth" | "identity" | "auth_manager";
  /** Thread / URL: open Add Secret or GCP connect dialog once Configure is showing the right section. */
  pendingCredentialModal?: null | "secret" | "gcp";
  onPendingCredentialModalConsumed?: () => void;
}

export function ConfigureTab({
  connection,
  environmentConnections,
  gcpConnections = [],
  secrets,
  userId = "default",
  cloudProvider,
  hasProject = true,
  projectId,
  workspaces,
  repoFullName = null,
  repoDefaultBranch = null,
  repos = [],
  secretsPreviewMode,
  secretsUseMockFallback = false,
  cloudAccountConnected = true,
  onCloudConnect,
  awsConnectExternalId,
  onChooseAnotherCloudProvider,
  onRequirementSatisfied,
  onChooseCloudProvider,
  onCloudDisconnected,
  initialSection,
  pendingCredentialModal = null,
  onPendingCredentialModalConsumed,
}: ConfigureTabProps) {
  const [activeSection, setActiveSection] = useState<ConfigureSection>(() => {
    const s = initialSection ?? "connection";
    if (s === "identity" || s === "auth_manager" || s === "secrets") return s;
    return "connection";
  });

  useEffect(() => {
    if (!initialSection) return;
    if (initialSection === "identity" || initialSection === "auth_manager" || initialSection === "secrets") {
      setActiveSection(initialSection);
      return;
    }
    setActiveSection("connection");
  }, [initialSection]);

  // Do not default to "aws": undefined/null must mean "no provider chosen" so we
  // show Choose Cloud Provider instead of incorrectly rendering AWSConnectionTab.
  const resolvedCloud = isResolvedCloudProvider(cloudProvider) ? cloudProvider : null;
  const needsCloudProviderChoice = hasProject && !resolvedCloud && !!onChooseCloudProvider;

  useEffect(() => {
    if (!pendingCredentialModal || !onPendingCredentialModalConsumed) return;
    if (pendingCredentialModal === "secret" && !hasProject) {
      onPendingCredentialModalConsumed();
      return;
    }
    if (
      pendingCredentialModal === "gcp" &&
      (resolvedCloud !== "gcp" || needsCloudProviderChoice)
    ) {
      onPendingCredentialModalConsumed();
    }
  }, [
    pendingCredentialModal,
    hasProject,
    resolvedCloud,
    needsCloudProviderChoice,
    onPendingCredentialModalConsumed,
  ]);

  const missingPoliciesCount = !resolvedCloud
    ? 0
    : resolvedCloud === "aws"
    ? (connection?.required_policies?.filter((p) => !p.validated).length || 0)
    : resolvedCloud === "gcp" && environmentConnections
    ? Object.values(environmentConnections).reduce((total, conn) => {
        return total + (conn?.required_apis?.filter((api: any) => !api.validated).length || 0);
      }, 0)
    : (connection?.required_apis?.filter((api: any) => !api.validated).length || 0);

  const pendingSecretsCount = secrets?.pending?.length || 0;

  return (
    <div className="h-full flex min-w-0 overflow-hidden bg-[var(--bg-primary)]">
      <SectionRail>
        <SectionRailButton
          active={activeSection === "connection"}
          icon={Cloud}
          label="Connection"
          count={missingPoliciesCount > 0 ? missingPoliciesCount : undefined}
          onClick={() => setActiveSection("connection")}
        />
        <SectionRailButton
          active={activeSection === "secrets"}
          icon={Key}
          label="Secrets"
          count={pendingSecretsCount > 0 ? pendingSecretsCount : undefined}
          onClick={() => setActiveSection("secrets")}
        />
        <SectionRailButton
          active={activeSection === "identity"}
          icon={Fingerprint}
          label="Identity"
          onClick={() => setActiveSection("identity")}
        />
        <SectionRailButton
          active={activeSection === "auth_manager"}
          icon={Vault}
          label="Auth manager"
          onClick={() => setActiveSection("auth_manager")}
        />
      </SectionRail>

      {/* Main Content */}
      <div className="flex-1 min-w-0 overflow-hidden">
        {!hasProject ? (
          <>
            {activeSection === "connection" && <ConnectionEmptyState />}
            {activeSection === "secrets" && <SecretsEmptyState />}
            {activeSection === "identity" && <IdentityEmptyState />}
            {activeSection === "auth_manager" && <AuthManagerEmptyState />}
            {/* {activeSection === "auth" && <AuthTab />} */}
          </>
        ) : (
          <>
            {activeSection === "connection" && needsCloudProviderChoice && (
              <ChooseCloudProviderEmptyState onChooseProvider={onChooseCloudProvider} />
            )}
            {activeSection === "connection" && resolvedCloud === "aws" && !needsCloudProviderChoice && (
              cloudAccountConnected ? (
                <AWSConnectionTab connection={connection as any} userId={userId} onDisconnected={onCloudDisconnected} />
              ) : (
                <AWSConnectEmptyState
                  onConnect={onCloudConnect}
                  userId={userId}
                  externalId={awsConnectExternalId}
                />
              )
            )}
            {activeSection === "connection" && resolvedCloud === "gcp" && !needsCloudProviderChoice && (
              cloudAccountConnected ? (
                <GCPConnectionTab
                  environmentConnections={environmentConnections || {}}
                  connections={gcpConnections}
                  userId={userId}
                  projectId={projectId}
                  workspaces={workspaces}
                  repoFullName={repoFullName}
                  repos={repos}
                  openCredentialModalRequest={pendingCredentialModal === "gcp"}
                  onOpenCredentialModalConsumed={onPendingCredentialModalConsumed}
                  onAddCloudProvider={onChooseAnotherCloudProvider}
                />
              ) : (
                <GCPConnectEmptyState
                  onConnect={onCloudConnect}
                  onChooseAnotherCloudProvider={onChooseAnotherCloudProvider}
                  userId={userId}
                  projectId={projectId}
                  workspaces={workspaces}
                  repoFullName={repoFullName}
                  repos={repos}
                  openCredentialModalRequest={pendingCredentialModal === "gcp"}
                  onOpenCredentialModalConsumed={onPendingCredentialModalConsumed}
                />
              )
            )}
            {activeSection === "secrets" && (
              <SecretsTab
                secrets={secrets}
                projectId={projectId}
                workspaces={workspaces}
                repoFullName={repoFullName}
                repoDefaultBranch={repoDefaultBranch}
                repos={repos}
                secretsPreviewMode={secretsPreviewMode}
                secretsUseMockFallback={secretsUseMockFallback}
                onRequirementSatisfied={onRequirementSatisfied}
                openCredentialModalRequest={pendingCredentialModal === "secret"}
                onOpenCredentialModalConsumed={onPendingCredentialModalConsumed}
              />
            )}
            {activeSection === "identity" && <AgentIdentityTab />}
            {activeSection === "auth_manager" && <AuthManagerTab />}
            {/* {activeSection === "auth" && <AuthTab />} */}
          </>
        )}
      </div>
    </div>
  );
}
