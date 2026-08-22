"use client";

import { Suspense, useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { CodebaseTab } from "@/components/interface/ops/codebase-tab";
import { ConfigureTab } from "@/components/interface/ops/configure-tab";
import { ChangesTab } from "@/components/interface/ops/changes-tab";
import { SubscriptionTab } from "@/components/interface/ops/subscription-tab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Cloud, FilePlus2, Github, Info, Code, Store } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/lib/auth-context";
import { useProject } from "@/lib/project-context";
import { useConsolePanel } from "@/components/layout/app-layout";
import { GitHubImportDialog, LinkGitHubDialog, CloudProviderSelectionDialog, AddRepositoryDialog } from "@/components/interface/project";
import { useProjectStream } from "@/hooks/useProjectStream";
import { useDemoOptional } from "@/lib/demo-context";
import MOCK_AI_STUDIO_CODEBASE from "@/components/interface/shared/mock-gcp-ai/mock-codebase.json";
import MOCK_ECOMMERCE_CODEBASE from "@/components/interface/shared/mock-aws/mock-codebase.json";
import awsOpsData from "@/components/interface/shared/mock-aws/mock-ops.json";
import gcpAiOpsData from "@/components/interface/shared/mock-gcp-ai/mock-ops.json";
const DEMO_OPS_DATA: Record<string, any> = {
  "ecommerce": awsOpsData,
  "ai-content-studio": gcpAiOpsData,
  "default": awsOpsData,
};

const DEMO_CODEBASES: Record<string, any> = {
  "ecommerce": MOCK_ECOMMERCE_CODEBASE,
  "ai-content-studio": MOCK_AI_STUDIO_CODEBASE,
  "default": MOCK_ECOMMERCE_CODEBASE,
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AWSConnectionStatus {
  connected: boolean;
  role_arn?: string;
  account_id?: string;
  role_name?: string;
  region?: string;
  last_validated?: string;
  external_id?: string;
}

interface GCPConnectionStatus {
  connected: boolean;
  project_id?: string;
  project_number?: string;
  service_account_email?: string;
  region?: string;
  last_validated?: string;
}

interface ProjectStatus {
  project_id: string;
  status: "idle" | "pending" | "analyzing" | "ready" | "error";
  analysis_stage?: string;
  contracts_count: number;
  architecture?: any;
  error?: string;
  thread_id?: string;
  thread_number?: number;
}

function SystemPageContent() {
  const searchParams = useSearchParams();
  const { isAuthenticated, user } = useAuth();
  const { currentProject, isLoading: isLoadingProject, setCurrentProject } = useProject();
  const { activeThreadId } = useConsolePanel();
  const demo = useDemoOptional();

  const configureSectionParam = searchParams.get("configureSection");
  const initialConfigureSection =
    configureSectionParam === "auth" ||
    configureSectionParam === "secrets" ||
    configureSectionParam === "connection" ||
    configureSectionParam === "identity" ||
    configureSectionParam === "auth_manager"
      ? configureSectionParam
      : undefined;

  const openCredentialModalParam = searchParams.get("openCredentialModal");
  const initialOpenCredentialModal =
    openCredentialModalParam === "secret" || openCredentialModalParam === "gcp"
      ? openCredentialModalParam
      : null;

  /** Thread CTAs can jump to Configure subsection without a full URL navigation. */
  const [navConfigureSection, setNavConfigureSection] = useState<
    "connection" | "secrets" | "auth" | "identity" | "auth_manager" | null
  >(null);

  /** One-shot: open Add Secret or GCP service-account dialog after navigating to Configure. */
  const [pendingCredentialModal, setPendingCredentialModal] = useState<
    null | "secret" | "gcp"
  >(null);

  useEffect(() => {
    setNavConfigureSection(null);
  }, [configureSectionParam]);

  const onPendingCredentialModalConsumed = useCallback(() => {
    setPendingCredentialModal(null);
  }, []);

  const effectiveConfigureSection = (navConfigureSection ?? initialConfigureSection) as
    | "connection"
    | "secrets"
    | "auth"
    | "identity"
    | "auth_manager"
    | undefined;

  // Tab state (CI/CD and Knowledge hidden until those surfaces are ready)
  const [activeTab, setActiveTab] = useState("code");
  const [inboxTick, setInboxTick] = useState(0);
  const [assumeSubscribed, setAssumeSubscribed] = useState(false);

  const setMainWorkspaceTab = useCallback((tab: string) => {
    if (tab === "pipeline" || tab === "knowledge") tab = "code";
    if (tab === "resources") tab = "changes";
    setActiveTab(tab);
  }, []);

  useEffect(() => {
    if (activeTab === "pipeline" || activeTab === "knowledge") setActiveTab("code");
    if (activeTab === "resources") setActiveTab("changes");
  }, [activeTab]);

  // Project status
  const [projectStatus, setProjectStatus] = useState<ProjectStatus | null>(null);
  const isAnalysisActive = projectStatus?.status === "pending" || projectStatus?.status === "analyzing";

  // Cloud connection state
  const [awsStatus, setAwsStatus] = useState<AWSConnectionStatus | null>(null);
  const [gcpStatus, setGcpStatus] = useState<GCPConnectionStatus | null>(null);
  const [gcpEnvironmentConnections, setGcpEnvironmentConnections] = useState<
    Record<string, any>
  >({});
  const [gcpConnections, setGcpConnections] = useState<
    {
      id: string;
      environment: string;
      gcp_project_id: string;
      gcp_project_number?: string | null;
      service_account_email?: string | null;
      default_region: string;
      workspace_id?: string | null;
      repo_full_name?: string | null;
      last_validated_at?: string | null;
      created_at?: string | null;
      is_active?: boolean;
    }[]
  >([]);
  const [isCloudLoading, setIsCloudLoading] = useState(true);
  const [requirements, setRequirements] = useState<any[]>([]);
  const [storedSecrets, setStoredSecrets] = useState<
    {
      id: string;
      secret_name: string;
      secret_arn?: string | null;
      workspace_id?: string | null;
      workspace_name?: string | null;
      workspace_path?: string | null;
      created_at?: string | null;
      updated_at?: string | null;
    }[]
  >([]);
  const [projectWorkspaces, setProjectWorkspaces] = useState<
    { id: string; name: string; workspace_path?: string | null; repo_url?: string | null }[]
  >([]);
  const [projectRepos, setProjectRepos] = useState<
    { full_name: string; default_branch: string; type: string }[]
  >([]);
  const [showCloudProviderDialog, setShowCloudProviderDialog] = useState(false);
  const [isUpdatingCloudProvider, setIsUpdatingCloudProvider] = useState(false);

  // Project import dialogs
  const [showGitHubImport, setShowGitHubImport] = useState(false);
  const [githubImportMode, setGitHubImportMode] = useState<"backend" | "frontend">("backend");
  const [showLinkGitHub, setShowLinkGitHub] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [showAddRepository, setShowAddRepository] = useState(false);
  const isGitHubLinked = user?.github_app_installed ?? false;

  // Demo state
  const [demoProjectSlug, setDemoProjectSlug] = useState("ecommerce");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("demo-project-slug");
      if (saved) setDemoProjectSlug(saved);
    }
  }, []);

  // Listen for demo project changes
  useEffect(() => {
    const handleDemoProjectChange = (e: CustomEvent<{ slug: string; fromApi?: boolean }>) => {
      setDemoProjectSlug(e.detail.slug);
      if (typeof window !== "undefined") {
        localStorage.setItem("demo-project-slug", e.detail.slug);
      }
    };
    window.addEventListener("demoProjectChanged", handleDemoProjectChange as unknown as EventListener);
    return () => {
      window.removeEventListener("demoProjectChanged", handleDemoProjectChange as unknown as EventListener);
    };
  }, []);

  // Deep-link: /?configureSection=secrets|auth|connection → Configure tab + sidebar section
  useEffect(() => {
    if (initialConfigureSection) setActiveTab("configure");
  }, [initialConfigureSection]);

  // Deep-link: ?openCredentialModal=secret|gcp opens the same credential dialogs as thread CTAs
  useEffect(() => {
    if (!initialOpenCredentialModal) return;
    setPendingCredentialModal(initialOpenCredentialModal);
    setActiveTab("configure");
    if (initialOpenCredentialModal === "secret") setNavConfigureSection("secrets");
    if (initialOpenCredentialModal === "gcp") {
      setNavConfigureSection("connection");
      if (!isAuthenticated) {
        setDemoProjectSlug("ai-content-studio");
        if (typeof window !== "undefined") {
          localStorage.setItem("demo-project-slug", "ai-content-studio");
        }
      }
    }
  }, [initialOpenCredentialModal, isAuthenticated]);

  // Listen for tab switch events from the thread (optional configureSection for Configure sidebar)
  useEffect(() => {
    const handler = (e: Event) => {
      const d = (e as CustomEvent<{
        tab?: string;
        configureSection?: string;
        openCredentialModal?: string;
      }>).detail;
      if (d?.tab) setMainWorkspaceTab(d.tab);
      if (
        d?.configureSection === "auth" ||
        d?.configureSection === "secrets" ||
        d?.configureSection === "connection" ||
        d?.configureSection === "identity" ||
        d?.configureSection === "auth_manager"
      ) {
        setNavConfigureSection(d.configureSection);
      }
      if (d?.openCredentialModal === "secret" || d?.openCredentialModal === "gcp") {
        setPendingCredentialModal(d.openCredentialModal);
      }
    };
    window.addEventListener("switchMainTab", handler);
    return () => {
      window.removeEventListener("switchMainTab", handler);
    };
  }, [setMainWorkspaceTab]);

  // Mock ops for guests — must exist before cloudProvider (same bundle as /ops).
  const effectiveDemoKey = !isAuthenticated ? demoProjectSlug : "default";
  const opsData = DEMO_OPS_DATA[effectiveDemoKey] || DEMO_OPS_DATA["default"];

  /** Synthetic project so Configure (secrets mocks, connection mocks) works when logged out.
   *  cloud_provider is always derived from demoProjectSlug (the source of truth for which
   *  demo is selected) so that switching demos via demoProjectChanged immediately updates
   *  the cloud provider even when the DemoContext project hasn't caught up yet. */
  const demoCloudProvider: "aws" | "gcp" = demoProjectSlug === "ai-content-studio" ? "gcp" : "aws";
  const guestConfigureProject: {
    id: string;
    name: string;
    status: string;
    cloud_provider: "aws" | "gcp";
  } | null =
    !isAuthenticated && opsData?.project
      ? demo?.project
        ? {
            id: `demo-${demo.project.slug}`,
            name: demo.project.name,
            status: "analyzing",
            cloud_provider: demoCloudProvider,
          }
        : {
            id: String((opsData.project as { id?: string }).id ?? `guest-${demoProjectSlug}`),
            name: String((opsData.project as { name?: string }).name ?? "Demo project"),
            status: "active",
            cloud_provider: demoCloudProvider,
          }
      : null;

  const configureProject = isAuthenticated ? currentProject : guestConfigureProject;

  // Cloud provider from project: only "aws" / "gcp" count as chosen; anything else → null
  const cloudProvider = isAuthenticated
    ? currentProject?.cloud_provider === "aws" || currentProject?.cloud_provider === "gcp"
      ? currentProject.cloud_provider
      : null
    : configureProject?.cloud_provider === "aws" || configureProject?.cloud_provider === "gcp"
      ? configureProject.cloud_provider
      : null;

  const hasChosenCloudProvider = cloudProvider === "aws" || cloudProvider === "gcp";

  // Fetch cloud connection status
  useEffect(() => {
    const fetchConnectionStatus = async () => {
      if (!isAuthenticated) {
        setIsCloudLoading(false);
        return;
      }

      try {
        const userId = user?.id || "default";
        if (cloudProvider === "aws") {
          const response = await fetch(`${API_URL}/api/aws/status?user_id=${userId}`, { credentials: "include" });
          if (response.ok) setAwsStatus(await response.json());
        } else if (cloudProvider === "gcp") {
          const path = currentProject?.id
            ? `${API_URL}/api/projects/${currentProject.id}/gcp-connections`
            : `${API_URL}/api/gcp/connections?user_id=${userId}`;
          const response = await fetch(path, { credentials: "include" });
          if (response.ok) {
            const payload = await response.json();
            const connections: any[] = Array.isArray(payload)
              ? payload
              : payload.connections || [];
            setGcpConnections(connections);
            const envMap: Record<string, any> = {};
            for (const conn of connections) {
              if (conn.is_active === false) continue;
              envMap[conn.environment] = {
                status: "connected",
                project_id: conn.gcp_project_id,
                project_number: conn.gcp_project_number,
                service_account_email: conn.service_account_email,
                region: conn.default_region || "us-central1",
                connected_at: conn.last_validated_at || conn.created_at || new Date().toISOString(),
              };
            }
            setGcpEnvironmentConnections(envMap);
            const primary = envMap.development || envMap.dev || envMap.default || Object.values(envMap)[0];
            setGcpStatus(
              primary
                ? { connected: true, project_id: primary.project_id, region: primary.region, last_validated: primary.connected_at }
                : { connected: false }
            );
          }
        }
      } catch (error) {
        console.error("Failed to fetch cloud status:", error);
        if (cloudProvider === "aws") setAwsStatus({ connected: false });
        else if (cloudProvider === "gcp") setGcpStatus({ connected: false });
      } finally {
        setIsCloudLoading(false);
      }
    };

    fetchConnectionStatus();
  }, [isAuthenticated, user?.id, cloudProvider, currentProject?.id]);

  // Fetch requirements
  useEffect(() => {
    if (!isAuthenticated || !currentProject?.id) return;
    const fetchRequirements = async () => {
      try {
        const res = await fetch(`${API_URL}/api/projects/${currentProject.id}/requirements?status=pending`, { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          setRequirements(data.requirements || []);
        }
      } catch (err) {
        console.error("Failed to fetch requirements:", err);
      }
    };
    fetchRequirements();
  }, [isAuthenticated, currentProject?.id]);

  const refreshConfigureSecretsData = useCallback(async () => {
    if (!isAuthenticated || !currentProject?.id) return;
    try {
      const [secRes, projRes, reqRes] = await Promise.all([
        fetch(`${API_URL}/api/projects/${currentProject.id}/secrets`, { credentials: "include" }),
        fetch(`${API_URL}/api/projects/${currentProject.id}`, { credentials: "include" }),
        fetch(`${API_URL}/api/projects/${currentProject.id}/requirements?status=pending`, {
          credentials: "include",
        }),
      ]);
      if (secRes.ok) {
        const d = await secRes.json();
        setStoredSecrets(d.secrets || []);
      } else {
        setStoredSecrets([]);
      }
      if (projRes.ok) {
        const d = await projRes.json();
        setProjectWorkspaces(Array.isArray(d.workspaces) ? d.workspaces : []);
        setProjectRepos(Array.isArray(d.repositories) ? d.repositories : []);
      } else {
        setProjectWorkspaces([]);
        setProjectRepos([]);
      }
      if (reqRes.ok) {
        const data = await reqRes.json();
        setRequirements(data.requirements || []);
      }
    } catch (err) {
      console.error("Failed to refresh configure / secrets data:", err);
    }
  }, [isAuthenticated, currentProject?.id]);

  useEffect(() => {
    void refreshConfigureSecretsData();
  }, [refreshConfigureSecretsData]);

  // SSE while import/analysis runs
  const shouldStream = !!(isAuthenticated && currentProject?.id && isAnalysisActive);
  useProjectStream(shouldStream ? currentProject?.id : null, {
    enabled: shouldStream,
    onComplete: () => fetchProjectStatus(),
    onError: (error) => {
      if (error !== "No active analysis run found") {
        console.error("[Stream] Error:", error);
      }
    },
  });

  // Fetch project status
  const fetchProjectStatus = useCallback(async () => {
    if (!currentProject?.id) return null;
    try {
      const response = await fetch(`${API_URL}/api/projects/${currentProject.id}/status`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setProjectStatus(data as ProjectStatus);
        return data as ProjectStatus;
      }
    } catch (error) {
      console.error("[ProjectStatus] Failed to fetch:", error);
    }
    return null;
  }, [currentProject?.id]);

  // Initial fetch when project changes
  useEffect(() => {
    if (!isAuthenticated || !currentProject) {
      setProjectStatus(null);
      return;
    }
    fetchProjectStatus();
  }, [isAuthenticated, currentProject, fetchProjectStatus]);

  // Cloud connection handlers
  const handleCloudConnect = () => {
    setIsCloudLoading(true);
    const userId = user?.id || "default";

    if (cloudProvider === "aws") {
      fetch(`${API_URL}/api/aws/status?user_id=${userId}`, { credentials: "include" })
        .then(res => res.json())
        .then(data => { setAwsStatus(data); setIsCloudLoading(false); })
        .catch(() => { setAwsStatus({ connected: true }); setIsCloudLoading(false); });
    } else if (cloudProvider === "gcp") {
      const path = currentProject?.id
        ? `${API_URL}/api/projects/${currentProject.id}/gcp-connections`
        : `${API_URL}/api/gcp/connections?user_id=${userId}`;
      fetch(path, { credentials: "include" })
        .then(res => res.json())
        .then((payload: any) => {
          const connections: any[] = Array.isArray(payload)
            ? payload
            : payload.connections || [];
          setGcpConnections(connections);
          const envMap: Record<string, any> = {};
          for (const conn of connections) {
            if (conn.is_active === false) continue;
            envMap[conn.environment] = {
              status: "connected",
              project_id: conn.gcp_project_id,
              project_number: conn.gcp_project_number,
              service_account_email: conn.service_account_email,
              region: conn.default_region || "us-central1",
              connected_at: conn.last_validated_at || conn.created_at || new Date().toISOString(),
            };
          }
          setGcpEnvironmentConnections(envMap);
          const primary = envMap.development || envMap.dev || envMap.default || Object.values(envMap)[0];
          setGcpStatus(
            primary
              ? { connected: true, project_id: primary.project_id, region: primary.region }
              : { connected: false }
          );
          setIsCloudLoading(false);
        })
        .catch(() => { setGcpStatus({ connected: true }); setIsCloudLoading(false); });
    } else {
      setIsCloudLoading(false);
    }
  };

  const handleCloudProviderSelected = async (provider: "aws" | "gcp") => {
    if (!currentProject?.id || provider === cloudProvider) {
      setShowCloudProviderDialog(false);
      return;
    }
    setIsUpdatingCloudProvider(true);
    try {
      const response = await fetch(`${API_URL}/api/projects/${currentProject.id}/cloud-provider`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cloud_provider: provider }),
      });
      if (!response.ok) throw new Error("Failed to update cloud provider");
      const updatedProject = await response.json();
      setCurrentProject({
        id: updatedProject.id,
        name: updatedProject.name,
        status: updatedProject.status,
        cloud_provider: updatedProject.cloud_provider,
      });
      setShowCloudProviderDialog(false);
      setAwsStatus(null);
      setGcpStatus(null);
    } catch (error) {
      console.error("Failed to update cloud provider:", error);
    } finally {
      setIsUpdatingCloudProvider(false);
    }
  };

  const handleCloudDisconnected = async () => {
    if (!currentProject?.id) {
      window.location.reload();
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/projects/${currentProject.id}/cloud-provider`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cloud_provider: null }),
      });
      if (response.ok) {
        const updated = await response.json();
        setCurrentProject({
          id: updated.id,
          name: updated.name,
          status: updated.status,
          cloud_provider: updated.cloud_provider,
        });
        setAwsStatus(null);
        setGcpStatus(null);
      } else {
        window.location.reload();
      }
    } catch {
      window.location.reload();
    }
  };

  const codebaseMockData = !isAuthenticated ? DEMO_CODEBASES[demoProjectSlug] : undefined;

  // Build connection data for ConfigureTab
  const buildConnectionData = () => {
    const { aws_connection, gcp_connection } = opsData;
    const defaultConn = {
      status: "not_connected",
      region: cloudProvider === "aws" ? "us-east-1" : "us-central1",
      connected_at: new Date().toISOString(),
    };

    if (cloudProvider === "aws" && awsStatus?.connected && awsStatus.account_id) {
      return {
        ...(aws_connection || defaultConn),
        account_id: awsStatus.account_id,
        role_arn: awsStatus.role_arn,
        region: awsStatus.region || "us-east-1",
        status: "connected",
        connected_at: awsStatus.last_validated || new Date().toISOString(),
        required_policies: (aws_connection?.required_policies || []).map((p: any) => ({ ...p, validated: true })),
      };
    }
    if (cloudProvider === "gcp" && gcpStatus?.connected && gcpStatus.project_id) {
      return {
        ...(gcp_connection || defaultConn),
        project_id: gcpStatus.project_id,
        project_number: gcpStatus.project_number,
        service_account_email: gcpStatus.service_account_email,
        region: gcpStatus.region || "us-central1",
        status: "connected",
        connected_at: gcpStatus.last_validated || new Date().toISOString(),
        required_apis: (gcp_connection?.required_apis || []).map((api: any) => ({ ...api, validated: true })),
      };
    }
    // Authenticated users who disconnected should not see mock data
    if (isAuthenticated) return defaultConn;
    return aws_connection || gcp_connection || defaultConn;
  };

  const workspacesFromOpsMock = useMemo(() => {
    const w = (opsData as { workspaces?: { id: string; name: string }[] }).workspaces;
    return Array.isArray(w) ? w : [];
  }, [opsData]);

  const secretsData = useMemo(() => {
    if (!isAuthenticated) return opsData.secrets;
    const apiConfigured = storedSecrets.map((s) => ({
      id: s.id,
      name: s.secret_name,
      type: "api_key",
      arn: s.secret_arn?.trim() || "",
      created_at: s.created_at || "",
      last_rotated: s.updated_at ?? null,
      referenced_by: [],
      status: "active",
      workspace_id: s.workspace_id ?? null,
      workspace_name: s.workspace_name ?? null,
      workspace_path: s.workspace_path ?? null,
    }));
    const apiPending = requirements
      .filter((r: any) => r.status === "pending" && (r.type === "credential_needed" || r.type === "info_needed"))
      .map((r: any) => ({
        id: r.id,
        name: r.title,
        type: r.type === "credential_needed" ? "api_key" : "text",
        description: r.reason,
        required_by: [],
        workspace_id: r.workspace_id ?? null,
        workspace_name: r.workspace_name ?? null,
      }));
    const hasApiActivity = apiConfigured.length > 0 || apiPending.length > 0;
    if (hasApiActivity) {
      return { configured: apiConfigured, pending: apiPending };
    }
    return { configured: [], pending: [] };
  }, [isAuthenticated, storedSecrets, requirements, opsData]);

  const workspacesForSecrets: {
    id: string;
    name: string;
    workspace_path?: string | null;
    repo_url?: string | null;
  }[] = isAuthenticated ? projectWorkspaces : workspacesFromOpsMock;

  const secretsRepo = useMemo(() => {
    const r = projectRepos.find((x) => x.type === "backend") || projectRepos[0];
    if (!r?.full_name) return { fullName: null as string | null, defaultBranch: null as string | null };
    return {
      fullName: r.full_name,
      defaultBranch: (r.default_branch || "main").trim() || "main",
    };
  }, [projectRepos]);

  const secretsRepos = useMemo(
    () =>
      projectRepos
        .filter((r) => typeof r.full_name === "string" && r.full_name.includes("/"))
        .map((r) => ({
          fullName: r.full_name,
          defaultBranch: (r.default_branch || "main").trim() || "main",
        })),
    [projectRepos],
  );

  const secretsUseMockFallback = false;

  const shouldShowCloudConnectionEmptyState =
    isAuthenticated &&
    !!currentProject &&
    ((cloudProvider === "aws" && (!awsStatus || !awsStatus.connected)) ||
      (cloudProvider === "gcp" && (!gcpStatus || !gcpStatus.connected)));

  // Badge counts
  const connectionData = buildConnectionData();
  const pendingSecretsCount = secretsData?.pending?.length || 0;
  const missingPoliciesCount = connectionData?.required_policies?.filter((p: any) => !p.validated).length || 0;
  const configBadgeCount = missingPoliciesCount + pendingSecretsCount;

  const changesBadgeCount = 0;

  if (!isAuthenticated) {
    return null;
  }

  // ─── Loading ───────────────────────────────────────────────────────
  if (isLoadingProject) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner className="text-[var(--text-primary)]" />
      </div>
    );
  }

  // ─── No project ────────────────────────────────────────────────────
  if (isAuthenticated && !currentProject) {
    return (
      <>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
              <Github className="h-5 w-5 text-[var(--text-secondary)]" />
            </div>
            <div className="flex items-center justify-center gap-2 mb-2">
              <h2 className="text-lg font-medium text-[var(--text-primary)]">No project yet</h2>
              <button
                onClick={() => setShowHowItWorks(true)}
                className="p-1 rounded-full hover:bg-[var(--bg-tertiary)] transition-colors"
                aria-label="How it works"
              >
                <Info className="h-4 w-4 text-[var(--text-secondary)]" strokeWidth={1} />
              </button>
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-6">
              Import an existing backend from GitHub to get started
            </p>
            <div className="flex flex-col gap-2">
              <Button
                onClick={() => {
                  if (!isGitHubLinked) { setShowLinkGitHub(true); return; }
                  setGitHubImportMode("backend");
                  setShowGitHubImport(true);
                }}
                className="bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                <Github className="h-4 w-4 mr-2" />
                Import Project
              </Button>
            </div>
          </div>
        </div>

        <GitHubImportDialog
          open={showGitHubImport}
          onOpenChange={setShowGitHubImport}
          defaultSourceRepoType={githubImportMode}
          onGoToProject={(project) => setCurrentProject(project)}
        />
        <LinkGitHubDialog open={showLinkGitHub} onOpenChange={setShowLinkGitHub} />

        <Dialog open={showHowItWorks} onOpenChange={setShowHowItWorks}>
          <DialogContent className="sm:max-w-[500px] bg-[var(--bg-primary)] border-[var(--border-color)]">
            <DialogHeader>
              <DialogTitle className="text-[var(--text-primary)]">How PatchAPI works</DialogTitle>
              <DialogDescription className="text-[var(--text-secondary)]">
                Test, debug, and fix your backend — end to end.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 py-4">
              {[
                { n: "1", title: "Connect Your Project", desc: "Import your backend from GitHub." },
                { n: "2", title: "Configure Access", desc: "Connect your cloud provider and add any required secrets." },
                { n: "3", title: "Describe What to Test", desc: "Tell the agent what to run — a flow, an endpoint, a scenario." },
                { n: "4", title: "Agent Runs, Debugs, Fixes", desc: "It executes, reads logs, finds issues, and fixes the code." },
              ].map((step) => (
                <div key={step.n} className="flex gap-3">
                  <div className="flex-shrink-0 h-6 w-6 rounded border border-[var(--border-color)] bg-[var(--bg-secondary)] flex items-center justify-center">
                    <span className="text-xs font-medium text-[var(--text-secondary)]">{step.n}</span>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{step.title}</h3>
                    <p className="text-xs text-[var(--text-secondary)]">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </DialogContent>
        </Dialog>
      </>
    );
  }

  // ─── Main workspace: Code, Configure, Changes, Subscription ──
  return (
    <>
      <Tabs value={activeTab} onValueChange={setMainWorkspaceTab} className="h-full flex flex-col">
        <div className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2 transition-colors">
          <TabsList className="inline-flex w-full h-9 items-center justify-between rounded-lg bg-[var(--bg-secondary)] p-1 text-[var(--text-secondary)] transition-colors">
            <TabsTrigger value="code" className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow">
              <Code className="w-3 h-3 mr-2" />
              Code
            </TabsTrigger>
            <TabsTrigger value="configure" className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow relative">
              <Cloud className="w-3 h-3 mr-2" />
              Configure
              {configBadgeCount > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {configBadgeCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="changes" className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow relative">
              <FilePlus2 className="w-3 h-3 mr-2" />
              Changes
              {changesBadgeCount > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {changesBadgeCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="subscription" className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow">
              <Store className="w-3 h-3 mr-2" />
              Subscription
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="code" className="flex-1 m-0 p-0 overflow-hidden">
          <CodebaseTab
            projectId={configureProject?.id || ""}
            threadId={activeThreadId}
            mockData={codebaseMockData}
            hasProject={!!configureProject || !isAuthenticated}
            onAddRepository={isAuthenticated ? () => {
              if (!isGitHubLinked) { setShowLinkGitHub(true); return; }
              if (configureProject) {
                setShowAddRepository(true);
                return;
              }
              setGitHubImportMode("backend");
              setShowGitHubImport(true);
            } : undefined}
          />
        </TabsContent>

        <TabsContent value="configure" className="flex-1 m-0 p-0 overflow-hidden">
          <ConfigureTab
            connection={connectionData}
            environmentConnections={
              cloudProvider === "gcp"
                ? (isAuthenticated && Object.keys(gcpEnvironmentConnections).length > 0
                    ? gcpEnvironmentConnections
                    : opsData.environment_connections)
                : undefined
            }
            gcpConnections={isAuthenticated ? gcpConnections : []}
            secrets={secretsData}
            userId={user?.id || "default"}
            cloudProvider={cloudProvider}
            hasProject={!!configureProject}
            projectId={configureProject?.id}
            workspaces={workspacesForSecrets}
            repoFullName={isAuthenticated ? secretsRepo.fullName : null}
            repoDefaultBranch={isAuthenticated ? secretsRepo.defaultBranch : null}
            repos={isAuthenticated ? secretsRepos : []}
            secretsPreviewMode={!isAuthenticated}
            secretsUseMockFallback={secretsUseMockFallback}
            cloudAccountConnected={!shouldShowCloudConnectionEmptyState}
            onCloudConnect={handleCloudConnect}
            awsConnectExternalId={awsStatus?.external_id}
            onChooseAnotherCloudProvider={
              isAuthenticated && currentProject && cloudProvider === "gcp"
                ? () => setShowCloudProviderDialog(true)
                : undefined
            }
            onChooseCloudProvider={
              isAuthenticated && currentProject && !hasChosenCloudProvider
                ? () => setShowCloudProviderDialog(true)
                : undefined
            }
            onCloudDisconnected={handleCloudDisconnected}
            onRequirementSatisfied={() => {
              void refreshConfigureSecretsData();
            }}
            initialSection={effectiveConfigureSection}
            pendingCredentialModal={pendingCredentialModal}
            onPendingCredentialModalConsumed={onPendingCredentialModalConsumed}
          />
        </TabsContent>

        <TabsContent value="changes" className="flex-1 m-0 p-0 overflow-hidden">
          <ChangesTab
            hasProject={!!configureProject}
            projectId={configureProject?.id}
            onBrowseSubscriptions={() => setMainWorkspaceTab("subscription")}
            userId={user?.id || "default"}
            workspaces={workspacesForSecrets}
            repos={isAuthenticated ? secretsRepos : []}
            secretsPreviewMode={!isAuthenticated}
          />
        </TabsContent>

        <TabsContent value="subscription" className="flex-1 m-0 p-0 overflow-hidden">
          <SubscriptionTab
            hasProject={!!configureProject}
            projectId={configureProject?.id}
            onOpenChanges={() => {
              setAssumeSubscribed(true);
              setInboxTick((tick) => tick + 1);
              setMainWorkspaceTab("changes");
            }}
          />
        </TabsContent>
      </Tabs>

      <CloudProviderSelectionDialog
        open={showCloudProviderDialog}
        onOpenChange={setShowCloudProviderDialog}
        onProviderSelected={handleCloudProviderSelected}
        currentProvider={
          cloudProvider === "aws" || cloudProvider === "gcp" ? cloudProvider : undefined
        }
        isSaving={isUpdatingCloudProvider}
      />

      <GitHubImportDialog
        open={showGitHubImport}
        onOpenChange={setShowGitHubImport}
        defaultSourceRepoType={githubImportMode}
        onGoToProject={(project) => setCurrentProject(project)}
      />
      <LinkGitHubDialog open={showLinkGitHub} onOpenChange={setShowLinkGitHub} />

      {configureProject && (
        <AddRepositoryDialog
          open={showAddRepository}
          onOpenChange={setShowAddRepository}
          projectId={configureProject.id}
          projectName={configureProject.name}
          onRepositoryAdded={() => {
            window.location.reload();
          }}
        />
      )}
    </>
  );
}

export default function SystemPage() {
  return (
    <Suspense
      fallback={
        <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-primary)]">
          <Spinner className="h-8 w-8 text-[var(--text-secondary)]" />
        </div>
      }
    >
      <SystemPageContent />
    </Suspense>
  );
}
