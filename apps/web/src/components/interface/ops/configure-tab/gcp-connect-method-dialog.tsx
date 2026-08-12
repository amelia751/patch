"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  CloudUpload,
  Copy,
  ExternalLink,
  Link2,
  X,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type GcpConnectEnvironmentOption = { value: string; label: string };

export type GcpAuthMethod = "oauth" | "wif" | "service_account";

interface GCPConnectMethodDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId: string;
  environment: string;
  onEnvironmentChange: (v: string) => void;
  environmentOptions: GcpConnectEnvironmentOption[];
  environmentHelpText?: string;
  onConnectSuccess?: () => void;
}

const REGION_OPTIONS = [
  { value: "us-central1", label: "us-central1 (Iowa)" },
  { value: "us-east1", label: "us-east1 (South Carolina)" },
  { value: "us-west1", label: "us-west1 (Oregon)" },
  { value: "europe-west1", label: "europe-west1 (Belgium)" },
  { value: "asia-east1", label: "asia-east1 (Taiwan)" },
] as const;

const PATCHAPI_AWS_ACCOUNT_ID = "093955289594";
const PATCHAPI_AWS_ROLE_NAME = "PatchAPIPlatformRole";
const PATCHAPI_AWS_STS_ROLE_ARN = `arn:aws:sts::${PATCHAPI_AWS_ACCOUNT_ID}:assumed-role/${PATCHAPI_AWS_ROLE_NAME}`;

const tabTriggerClass =
  "text-xs font-medium rounded-md px-2 py-1.5 text-[var(--text-secondary)] data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-primary)] data-[state=active]:shadow-sm";

/** GCP Console buttons, menu items, and dialog titles — reads as UI, not body text. */
function GcpUiLabel({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded-md border border-primary/35 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold leading-snug text-[var(--text-primary)] align-baseline mx-0.5 shadow-sm"
      translate="no"
    >
      {children}
    </span>
  );
}

/** Form field / section labels in the GCP wizard (Name, Pool ID, etc.). */
function GcpFieldLabel({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded border border-[var(--border-color)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--text-primary)] align-baseline mx-0.5"
      translate="no"
    >
      {children}
    </span>
  );
}

export function GCPConnectMethodDialog({
  open,
  onOpenChange,
  userId,
  environment,
  onEnvironmentChange,
  environmentOptions,
  environmentHelpText,
  onConnectSuccess,
}: GCPConnectMethodDialogProps) {
  const [authMethod, setAuthMethod] = useState<GcpAuthMethod>("wif");
  const [selectedRegion, setSelectedRegion] = useState("us-central1");
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connectionErrorStep, setConnectionErrorStep] = useState<number | null>(null);
  const [connectionSuccess, setConnectionSuccess] = useState(false);

  // SA-specific
  const [gcpProjectId, setGcpProjectId] = useState("");
  const [serviceAccountJson, setServiceAccountJson] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);

  // WIF-specific
  const [wifIamPrincipal, setWifIamPrincipal] = useState("");
  const [wifProviderResource, setWifProviderResource] = useState("");
  const [wifServiceAccountEmail, setWifServiceAccountEmail] = useState("");

  // Shared
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const projectForConsoleLinks = gcpProjectId.trim();
  /** GCP project id or number for console deep links (SA tab upload or WIF provider resource). */
  const consoleProject =
    projectForConsoleLinks ||
    (() => {
      const parts = wifProviderResource.trim().split("/");
      return parts.length >= 2 && parts[0] === "projects" ? parts[1] : "";
    })();
  const gcpConsoleServiceAccountsUrl = consoleProject
    ? `https://console.cloud.google.com/iam-admin/serviceaccounts?project=${encodeURIComponent(consoleProject)}`
    : "https://console.cloud.google.com/iam-admin/serviceaccounts";
  const gcpConsoleWifPoolsUrl = consoleProject
    ? `https://console.cloud.google.com/iam-admin/workload-identity-pools?project=${encodeURIComponent(consoleProject)}`
    : "https://console.cloud.google.com/iam-admin/workload-identity-pools";
  const gcpConsoleWifPoolDetailUrl = consoleProject
    ? `https://console.cloud.google.com/iam-admin/workload-identity-pools/pool/patchapi-pool?project=${encodeURIComponent(consoleProject)}`
    : "https://console.cloud.google.com/iam-admin/workload-identity-pools";
  const gcpConsoleWifProviderUrl = consoleProject
    ? `https://console.cloud.google.com/iam-admin/workload-identity-pools/pool/patchapi-pool/provider/patchapi-aws?project=${encodeURIComponent(consoleProject)}`
    : "https://console.cloud.google.com/iam-admin/workload-identity-pools";

  const resetForm = () => {
    setConnectionError(null);
    setConnectionErrorStep(null);
    setConnectionSuccess(false);
    setServiceAccountJson("");
    setGcpProjectId("");
    setWifIamPrincipal("");
    setWifProviderResource("");
    setWifServiceAccountEmail("");
    setIsConnecting(false);
    setAuthMethod("wif");
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) resetForm();
    onOpenChange(next);
  };

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const onSuccess = () => {
    setConnectionSuccess(true);
    setTimeout(() => {
      handleOpenChange(false);
      if (onConnectSuccess) onConnectSuccess();
      else window.location.reload();
    }, 1500);
  };

  // --- OAuth handler ---
  const handleOAuthConnect = async () => {
    setIsConnecting(true);
    setConnectionError(null);
    try {
      const params = new URLSearchParams({
        user_id: userId,
        region: selectedRegion,
        environment,
      });
      const response = await fetch(
        `${API_URL}/api/gcp/oauth/authorize?${params}`,
        { credentials: "include" }
      );
      if (response.ok) {
        const data = await response.json();
        window.location.href = data.authorization_url;
      } else {
        const data = await response.json().catch(() => ({}));
        setConnectionError(
          data.detail ||
            "Google sign-in is not configured for this deployment yet."
        );
      }
    } catch {
      setConnectionError(
        "Unable to start Google sign-in. The OAuth endpoint may not be deployed yet."
      );
    } finally {
      setIsConnecting(false);
    }
  };

  // --- WIF handler ---
  const handleWifConnect = async () => {
    if (!wifProviderResource.trim()) {
      setConnectionError("Enter the Workload Identity Provider resource name.");
      setConnectionErrorStep(null);
      return;
    }
    if (!wifServiceAccountEmail.trim()) {
      setConnectionError("Enter the service account email to impersonate.");
      setConnectionErrorStep(null);
      return;
    }

    setIsConnecting(true);
    setConnectionError(null);
    setConnectionErrorStep(null);
    try {
      const response = await fetch(`${API_URL}/api/gcp/wif/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          provider_resource_name: wifProviderResource,
          service_account_email: wifServiceAccountEmail,
          user_id: userId,
          region: selectedRegion,
          environment,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.connected) {
        onSuccess();
      } else {
        const detail = data.detail;
        if (detail && typeof detail === "object" && detail.message) {
          setConnectionError(detail.message);
          setConnectionErrorStep(detail.step ?? null);
        } else {
          setConnectionError(
            (typeof detail === "string" ? detail : null) ||
              "WIF connection endpoint is not available for this deployment yet."
          );
          setConnectionErrorStep(null);
        }
      }
    } catch {
      setConnectionError(
        "Unable to reach the server. The WIF endpoint may not be deployed yet."
      );
      setConnectionErrorStep(null);
    } finally {
      setIsConnecting(false);
    }
  };

  // --- SA JSON handler ---
  const processFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const json = event.target?.result as string;
        const parsed = JSON.parse(json);
        if (parsed.type === "service_account" && parsed.project_id) {
          setServiceAccountJson(json);
          setGcpProjectId(parsed.project_id);
          setConnectionError(null);
        } else {
          setConnectionError("Invalid service account key file.");
        }
      } catch {
        setConnectionError("Failed to parse JSON file.");
      }
    };
    reader.readAsText(file);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".json")) {
      setConnectionError("Please upload a JSON file.");
      return;
    }
    processFile(file);
  };

  const handleServiceAccountConnect = async () => {
    if (!serviceAccountJson.trim()) {
      setConnectionError("Please upload a service account key file.");
      return;
    }
    if (!gcpProjectId.trim()) {
      setConnectionError("Project ID not found in the JSON file.");
      return;
    }
    setIsConnecting(true);
    setConnectionError(null);
    try {
      const response = await fetch(`${API_URL}/api/gcp/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: gcpProjectId,
          credentials_json: serviceAccountJson,
          user_id: userId,
          region: selectedRegion,
          environment,
        }),
      });
      const data = await response.json();
      if (response.ok && data.connected) {
        onSuccess();
      } else {
        setConnectionError(data.detail || data.error || "Failed to connect.");
      }
    } catch {
      setConnectionError(
        "Network error. Please check if the backend is running."
      );
    } finally {
      setIsConnecting(false);
    }
  };

  // --- primary action per method ---
  const handlePrimaryAction = () => {
    if (authMethod === "wif") handleWifConnect();
    else handleServiceAccountConnect();
  };

  const isPrimaryDisabled = (() => {
    if (isConnecting || connectionSuccess) return true;
    if (authMethod === "service_account")
      return !serviceAccountJson.trim() || !gcpProjectId.trim();
    if (authMethod === "wif")
      return (
        !wifProviderResource.trim() || !wifServiceAccountEmail.trim()
      );
    return false;
  })();

  const primaryLabel = (() => {
    if (isConnecting)
      return (
        <>
          <Spinner className="h-4 w-4 mr-2" />
          <span className="shimmer-text">Connecting</span>
        </>
      );
    if (connectionSuccess)
      return (
        <>
          <CheckCircle2 className="h-4 w-4 mr-2" />
          Connected!
        </>
      );
    if (authMethod === "wif") return "Connect via WIF";
    return "Connect GCP project";
  })();

  // --- copyable value helper ---
  const CopyableValue = ({
    label,
    value,
    field,
    mono,
  }: {
    label: string;
    value: string;
    field: string;
    mono?: boolean;
  }) => (
    <div className="space-y-1">
      <label className="text-[10px] font-medium text-[var(--text-secondary)]">
        {label}
      </label>
      <div className="flex items-center gap-1.5 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-md px-2.5 py-1.5">
        <span
          className={cn(
            "flex-1 text-[10px] text-[var(--text-primary)] break-all select-all",
            mono && "font-mono"
          )}
        >
          {value}
        </span>
        <button
          type="button"
          onClick={() => handleCopy(value, field)}
          className="p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors shrink-0"
        >
          {copiedField === field ? (
            <Check className="h-3 w-3 text-[#10b981]" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </button>
      </div>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] max-h-[90vh] overflow-y-auto">
        <DialogHeader className="mt-3 space-y-3">
          <div className="flex items-center gap-2">
            <img src="/google-cloud.svg" alt="" className="h-6 w-6 shrink-0" />
            <DialogTitle className="text-sm font-medium text-[var(--text-primary)]">
              Connect GCP project
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-[var(--text-secondary)]">
            Choose how PatchAPI authenticates to your GCP project. All methods
            store credentials securely and scope access to agent-created
            resources.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={authMethod}
          onValueChange={(v) => {
            setAuthMethod(v as GcpAuthMethod);
            setConnectionError(null);
            setConnectionErrorStep(null);
          }}
          className="pt-2"
        >
          <TabsList className="grid h-auto w-full grid-cols-2 gap-1 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)] p-1 text-[var(--text-secondary)]">
            <TabsTrigger value="wif" className={tabTriggerClass}>
              Workload Identity
            </TabsTrigger>
            <TabsTrigger value="service_account" className={tabTriggerClass}>
              Service account
            </TabsTrigger>
          </TabsList>

          <div className="space-y-4 mt-3">
          {/* ---------- WIF ---------- */}
          <TabsContent value="wif" className="mt-0 space-y-4 focus-visible:outline-none">
              <div className="p-2.5 bg-primary/10 border border-primary/20 rounded-lg">
                <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                  <span className="font-medium text-primary">
                    Federated trust:
                  </span>{" "}
                  PatchAPI&apos;s own AWS identity exchanges tokens with your GCP
                  project — no long-lived keys, no human dependency. Google
                  recommends WIF for cross-cloud workloads. Setup takes ~15 min
                  in the GCP Console.
                </p>
              </div>

              {/* PatchAPI identity to share */}
              <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Link2 className="h-3.5 w-3.5 text-primary" />
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    PatchAPI&apos;s AWS identity
                  </h3>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)]">
                  You&apos;ll need these values when creating the Workload
                  Identity Provider in your GCP project.
                </p>
                <div className="space-y-2">
                  <CopyableValue
                    label="AWS Account ID"
                    value={PATCHAPI_AWS_ACCOUNT_ID}
                    field="aws-account"
                    mono
                  />
                  <CopyableValue
                    label="Assumed Role ARN"
                    value={PATCHAPI_AWS_STS_ROLE_ARN}
                    field="aws-role"
                    mono
                  />
                </div>
              </div>

              {/* Step 1 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 1 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 1: Create Workload Identity Pool
                  </h3>
                  <a
                    href={gcpConsoleWifPoolsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)]">
                  A pool groups external identities that can access your GCP resources.
                </p>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>Click <GcpUiLabel>Create Pool</GcpUiLabel></li>
                    <li>
                      Set <GcpFieldLabel>Name</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-pool" field="pool-name" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Pool ID</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-pool" field="pool-id" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Description</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="Allows PatchAPI to access GCP resources via AWS federation" field="pool-desc" /></div>
                    </li>
                    <li>Leave the <GcpUiLabel>Enabled pool</GcpUiLabel> toggle on</li>
                    <li>Click <GcpUiLabel>Continue</GcpUiLabel></li>
                  </ol>
                </div>
              </div>

              {/* Step 2 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 2 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 2: Add AWS provider
                  </h3>
                  <a
                    href={gcpConsoleWifPoolDetailUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)]">
                  This tells GCP to trust PatchAPI&apos;s AWS identity for token exchange.
                </p>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>
                      Select provider type: <GcpUiLabel>AWS</GcpUiLabel>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Provider name</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-aws" field="provider-name" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Provider ID</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-aws" field="provider-id" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>AWS Account ID</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value={PATCHAPI_AWS_ACCOUNT_ID} field="aws-account-step2" mono /></div>
                    </li>
                    <li>Leave <GcpFieldLabel>Audiences</GcpFieldLabel> as default</li>
                    <li>Click <GcpUiLabel>Continue</GcpUiLabel></li>
                  </ol>
                </div>
              </div>

              {/* Step 3 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 3 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 3: Configure attribute mapping
                  </h3>
                  <a
                    href={gcpConsoleWifProviderUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)]">
                  Map AWS attributes so GCP can identify PatchAPI&apos;s role, then add a condition
                  that restricts the pool to only that role.
                </p>

                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>
                      GCP pre-fills default mappings. Verify they match the two rows below — if the
                      second row differs, replace the CEL expression with the value shown:
                    </li>
                  </ol>
                </div>

                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-2">
                  <p className="text-[10px] font-medium text-[var(--text-primary)]">Required attribute mappings</p>
                  <div className="space-y-1.5">
                    <div className="flex items-start gap-2 text-[9px]">
                      <span className="text-[var(--text-secondary)] shrink-0 w-28">google.subject</span>
                      <span className="text-[var(--text-secondary)]">→</span>
                      <CopyableValue label="" value="assertion.arn" field="map-subject" mono />
                    </div>
                    <div className="flex items-start gap-2 text-[9px]">
                      <span className="text-[var(--text-secondary)] shrink-0 w-28">attribute.aws_role</span>
                      <span className="text-[var(--text-secondary)]">→</span>
                      <CopyableValue label="" value="assertion.arn.extract('assumed-role/{role}/')" field="map-role" mono />
                    </div>
                  </div>
                  <p className="text-[9px] text-[var(--text-secondary)] mt-1">
                    This extracts just the role name (e.g. <code className="text-[8px] bg-[var(--bg-tertiary)] px-0.5 rounded">{PATCHAPI_AWS_ROLE_NAME}</code>) from the full AWS ARN.
                  </p>
                </div>

                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside" start={2}>
                    <li>
                      Scroll down to the <GcpFieldLabel>Attribute Conditions</GcpFieldLabel> section
                    </li>
                    <li>
                      Click <GcpUiLabel>Add Condition</GcpUiLabel>
                    </li>
                    <li>
                      Paste the condition below — this restricts the pool to only PatchAPI&apos;s IAM role
                    </li>
                  </ol>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] font-medium text-[var(--text-secondary)]">
                    Condition expression
                  </label>
                  <div className="relative bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-md p-3">
                    <pre className="text-[10px] font-mono text-[var(--text-primary)] whitespace-pre-wrap break-all select-all leading-relaxed">
{`attribute.aws_role == "${PATCHAPI_AWS_ROLE_NAME}"`}
                    </pre>
                    <button
                      type="button"
                      onClick={() => handleCopy(
                        `attribute.aws_role == "${PATCHAPI_AWS_ROLE_NAME}"`,
                        "attr-condition"
                      )}
                      className="absolute top-2 right-2 p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                    >
                      {copiedField === "attr-condition" ? (
                        <Check className="h-3.5 w-3.5 text-[#10b981]" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-1.5 list-decimal list-inside" start={5}>
                    <li>
                      Click <GcpUiLabel>Save</GcpUiLabel>
                    </li>
                  </ol>
                </div>
              </div>

              {!consoleProject && (
                <p className="text-[9px] text-[var(--text-secondary)] px-1">
                  Paste the <GcpFieldLabel>IAM principal</GcpFieldLabel> in the field below so every <GcpUiLabel>Open GCP Console</GcpUiLabel> link opens the correct project automatically.
                </p>
              )}

              {/* Step 4 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 4 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 4: Viewer service account
                  </h3>
                  <a
                    href={gcpConsoleServiceAccountsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)]">
                  PatchAPI will impersonate this service account. Create <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">patchapi-viewer</code> here if needed, or open it to add missing project roles.
                </p>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>
                      Open the link above, then either click <GcpUiLabel>Create service account</GcpUiLabel> or open <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">patchapi-viewer</code> → <GcpUiLabel>Permissions</GcpUiLabel> → <GcpUiLabel>Grant access</GcpUiLabel> to add roles
                    </li>
                    <li>
                      Set <GcpFieldLabel>Service account name</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-viewer" field="sa-name" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Service account ID</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="patchapi-viewer" field="sa-id" mono /></div>
                    </li>
                    <li>
                      Set <GcpFieldLabel>Service account description</GcpFieldLabel>:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value="Read-only access for PatchAPI to observe services, logs, and config" field="sa-desc" /></div>
                    </li>
                    <li>Click <GcpUiLabel>Create and continue</GcpUiLabel></li>
                    <li>
                      Under <GcpFieldLabel>Grant this service account access to project</GcpFieldLabel>, search and add each role:
                      <div className="mt-1.5 ml-1 space-y-1.5">
                        <CopyableValue label="" value="Cloud Run Viewer" field="role-run" mono />
                        <CopyableValue label="" value="Cloud Functions Viewer" field="role-fn" mono />
                        <CopyableValue label="" value="Cloud SQL Viewer" field="role-sql" mono />
                        <CopyableValue label="" value="Logs Viewer" field="role-logs" mono />
                        <CopyableValue label="" value="Monitoring Viewer" field="role-mon" mono />
                        <CopyableValue label="" value="Service Usage Consumer" field="role-svc" mono />
                        <CopyableValue label="" value="Secret Manager Secret Accessor" field="role-sm" mono />
                      </div>
                      <p className="text-[9px] text-[var(--text-secondary)] mt-1.5 ml-1">
                        Secret Manager access lets PatchAPI pull Cloud Run secrets at sandbox boot — no secrets are stored, only read transiently.
                      </p>
                    </li>
                    <li>Click <GcpUiLabel>Continue</GcpUiLabel>, then <GcpUiLabel>Done</GcpUiLabel></li>
                  </ol>
                </div>
              </div>

              {/* Step 5 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 5 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 5: Grant the pool access to impersonate the service account
                  </h3>
                  <a
                    href={gcpConsoleWifPoolsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>
                      Open <GcpUiLabel>Workload Identity Federation</GcpUiLabel> and select pool{" "}
                      <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">patchapi-pool</code>
                    </li>
                    <li>Click <GcpUiLabel>Grant Access</GcpUiLabel></li>
                    <li>
                      Select{" "}
                      <GcpUiLabel>Grant access using service account impersonation</GcpUiLabel>
                    </li>
                    <li>
                      For <GcpFieldLabel>Service account</GcpFieldLabel>, select{" "}
                      <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">patchapi-viewer</code>
                    </li>
                    <li>
                      For <GcpFieldLabel>attribute name</GcpFieldLabel>, select{" "}
                      <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">aws_role</code>
                    </li>
                    <li>
                      For <GcpFieldLabel>attribute value</GcpFieldLabel>, paste:
                      <div className="mt-1.5 ml-1"><CopyableValue label="" value={PATCHAPI_AWS_ROLE_NAME} field="aws-role-step5" mono /></div>
                    </li>
                    <li>Click <GcpUiLabel>Save</GcpUiLabel></li>
                    <li>
                      A <GcpUiLabel>Configure your application</GcpUiLabel> dialog may appear — you don&apos;t need to download anything. Click <GcpUiLabel>Dismiss</GcpUiLabel>.
                    </li>
                  </ol>
                </div>
              </div>

              {/* Step 6 */}
              <div className={`border rounded-lg p-4 space-y-3 ${connectionErrorStep === 6 ? "border-red-500/60 bg-red-500/5" : "border-[var(--border-color)]"}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <h3 className="text-xs font-medium text-[var(--text-primary)]">
                    Step 6: Copy the IAM principal
                  </h3>
                  <a
                    href={gcpConsoleWifPoolDetailUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-3 list-decimal list-inside">
                    <li>
                      Click the link above to open the <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">patchapi-pool</code> detail page
                    </li>
                    <li>
                      Find the <GcpFieldLabel>IAM principal</GcpFieldLabel> value and copy it
                    </li>
                    <li>
                      Paste it into the field below
                    </li>
                  </ol>
                </div>
              </div>

              {/* WIF inputs */}
              <div className="space-y-3">
                <div className="space-y-2">
                  <label className="text-xs font-medium text-[var(--text-primary)]">
                    IAM principal
                  </label>
                  <Input
                    value={wifIamPrincipal}
                    onChange={(e) => {
                      const raw = e.target.value;
                      setWifIamPrincipal(raw);
                      const match = raw.match(
                        /projects\/(\d+)\/locations\/global\/workloadIdentityPools\/([^/]+)/
                      );
                      if (match) {
                        const [, projectNumber, poolId] = match;
                        setWifProviderResource(
                          `projects/${projectNumber}/locations/global/workloadIdentityPools/${poolId}/providers/patchapi-aws`
                        );
                      }
                    }}
                    placeholder="principal://iam.googleapis.com/projects/123456/locations/global/workloadIdentityPools/patchapi-pool/subject/..."
                    className="h-9 text-xs font-mono bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
                  />
                  <p className="text-[9px] text-[var(--text-secondary)]">
                    Shown on the pool detail page under <GcpFieldLabel>IAM principal</GcpFieldLabel>
                  </p>
                </div>

                {wifProviderResource && (
                  <div className="space-y-2">
                    <label className="text-[10px] font-medium text-[var(--text-secondary)]">
                      Provider resource name (auto-filled)
                    </label>
                    <div className="flex items-center gap-1.5 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-md px-2.5 py-1.5">
                      <span className="flex-1 text-[10px] font-mono text-[var(--text-primary)] break-all select-all">
                        {wifProviderResource}
                      </span>
                      <CheckCircle2 className="h-3 w-3 text-[#10b981] shrink-0" />
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-[var(--text-primary)]">
                      Service account email
                    </label>
                    <a
                      href={consoleProject
                        ? `https://console.cloud.google.com/iam-admin/serviceaccounts?project=${encodeURIComponent(consoleProject)}`
                        : "https://console.cloud.google.com/iam-admin/serviceaccounts"
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] text-primary hover:underline flex items-center gap-1"
                    >
                      View service accounts
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <Input
                    value={wifServiceAccountEmail}
                    onChange={(e) =>
                      setWifServiceAccountEmail(e.target.value)
                    }
                    placeholder="patchapi-viewer@your-project.iam.gserviceaccount.com"
                    className="h-9 text-xs font-mono bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
                  />
                </div>
              </div>
          </TabsContent>

          {/* ---------- SA JSON ---------- */}
          <TabsContent value="service_account" className="mt-0 space-y-4 focus-visible:outline-none">
              <div className="p-2.5 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg">
                <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                  <span className="font-medium text-[var(--text-primary)]">
                    Service account consent:
                  </span>{" "}
                  You create a dedicated read-only identity in GCP and download a
                  JSON key. PatchAPI stores it encrypted in AWS Secrets Manager.
                  Stable for small teams, but many organizations{" "}
                  <a
                    href="https://cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts#disable_service_account_key_creation"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    block key creation
                  </a>
                  . If blocked, use{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMethod("wif");
                      setConnectionError(null);
                      setConnectionErrorStep(null);
                    }}
                    className="text-primary hover:underline font-medium"
                  >
                    WIF
                  </button>
                  .
                </p>
              </div>

              <div className="p-2.5 bg-primary/10 border border-primary/20 rounded-lg">
                <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                  <span className="font-medium text-primary">
                    Secure access:
                  </span>{" "}
                  The platform uses these credentials to manage resources in
                  your GCP project. Only resources created by the agent will be
                  managed.
                </p>
              </div>

              {/* Step 1 */}
              <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">
                    Step 1: Create service account
                  </h3>
                  <a
                    href={
                      projectForConsoleLinks
                        ? `https://console.cloud.google.com/iam-admin/serviceaccounts/create?project=${encodeURIComponent(projectForConsoleLinks)}`
                        : "https://console.cloud.google.com/iam-admin/serviceaccounts"
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-1 list-decimal list-inside">
                    <li>
                      Click <GcpUiLabel>Create Service Account</GcpUiLabel>
                    </li>
                    <li>
                      Enter name:{" "}
                      <code className="text-[9px] bg-[var(--bg-tertiary)] px-1 rounded">
                        patchapi-viewer
                      </code>
                    </li>
                    <li>
                      Grant these roles (search and add each one):
                      <div className="mt-1.5 ml-1 space-y-1.5">
                        <CopyableValue label="" value="Cloud Run Viewer" field="sa-role-run" mono />
                        <CopyableValue label="" value="Cloud Functions Viewer" field="sa-role-fn" mono />
                        <CopyableValue label="" value="Cloud SQL Viewer" field="sa-role-sql" mono />
                        <CopyableValue label="" value="Logs Viewer" field="sa-role-logs" mono />
                        <CopyableValue label="" value="Monitoring Viewer" field="sa-role-mon" mono />
                        <CopyableValue label="" value="Service Usage Consumer" field="sa-role-svc" mono />
                        <CopyableValue label="" value="Secret Manager Secret Accessor" field="sa-role-sm" mono />
                      </div>
                      <p className="text-[9px] text-[var(--text-secondary)] mt-1.5 ml-1">
                        Secret Manager access lets PatchAPI pull Cloud Run secrets at sandbox boot — no secrets are stored, only read transiently.
                      </p>
                    </li>
                    <li>
                      Click <GcpUiLabel>Done</GcpUiLabel>
                    </li>
                  </ol>
                </div>
              </div>

              {/* Step 2 */}
              <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">
                    Step 2: Create and download key
                  </h3>
                  <a
                    href={
                      projectForConsoleLinks
                        ? `https://console.cloud.google.com/iam-admin/serviceaccounts?project=${encodeURIComponent(projectForConsoleLinks)}`
                        : "https://console.cloud.google.com/iam-admin/serviceaccounts"
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0"
                  >
                    Open GCP Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-1 list-decimal list-inside">
                    <li>Find your service account in the list</li>
                    <li>
                      Click <GcpUiLabel>Actions (⋮)</GcpUiLabel> →{" "}
                      <GcpUiLabel>Manage keys</GcpUiLabel>
                    </li>
                    <li>
                      Click <GcpUiLabel>Add Key</GcpUiLabel> →{" "}
                      <GcpUiLabel>Create new key</GcpUiLabel>
                    </li>
                    <li>
                      Select <GcpFieldLabel>JSON</GcpFieldLabel> format
                    </li>
                    <li>
                      Click <GcpUiLabel>Create</GcpUiLabel> — the
                      key file downloads automatically
                    </li>
                  </ol>
                  <div className="mt-3 p-2 bg-amber-500/10 border border-amber-500/20 rounded">
                    <p className="text-[9px] text-amber-700 dark:text-amber-300">
                      <strong>Important:</strong> Keep this JSON file secure. It
                      grants access according to the service account&apos;s IAM
                      roles.
                    </p>
                  </div>
                </div>
              </div>

              {/* Upload */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-[var(--text-primary)]">
                  Upload service account key (JSON)
                </label>
                <div className="relative">
                  <input
                    type="file"
                    accept=".json,application/json"
                    onChange={handleFileUpload}
                    className="hidden"
                    id="gcp-service-account-upload"
                  />
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className={cn(
                      "relative flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer transition-colors",
                      serviceAccountJson
                        ? "border-[#10b981] bg-[#10b981]/5"
                        : isDragOver
                          ? "border-primary bg-primary/10"
                          : "border-[var(--border-color)] hover:border-primary hover:bg-[var(--bg-secondary)]"
                    )}
                    onClick={() =>
                      !serviceAccountJson &&
                      document
                        .getElementById("gcp-service-account-upload")
                        ?.click()
                    }
                  >
                    {serviceAccountJson && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setServiceAccountJson("");
                          setGcpProjectId("");
                          setConnectionError(null);
                          const input = document.getElementById(
                            "gcp-service-account-upload"
                          ) as HTMLInputElement;
                          if (input) input.value = "";
                        }}
                        className="absolute top-2 right-2 p-1 rounded-full bg-[var(--bg-tertiary)] hover:bg-[var(--border-color)] text-[var(--text-secondary)] transition-colors"
                        title="Remove uploaded file"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {serviceAccountJson ? (
                      <>
                        <CheckCircle2 className="h-8 w-8 text-[#10b981] mb-2" />
                        <p className="text-xs text-[#10b981] font-medium">
                          Service account key uploaded
                        </p>
                        <p className="text-[10px] text-[var(--text-secondary)] mt-1">
                          Project: {gcpProjectId}
                        </p>
                      </>
                    ) : (
                      <>
                        <CloudUpload className="h-6 w-6 text-[var(--text-secondary)] mb-2" />
                        <p className="text-xs text-[var(--text-primary)] font-medium">
                          Click to upload JSON key file
                        </p>
                        <p className="text-[10px] text-[var(--text-secondary)] mt-1">
                          or drag and drop
                        </p>
                      </>
                    )}
                  </div>
                </div>
              </div>
          </TabsContent>

          {/* ── Common: region + environment ── */}
          <div className="space-y-3 pt-1 border-t border-[var(--border-color)]">
            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                Default region
              </label>
              <Select value={selectedRegion} onValueChange={setSelectedRegion}>
                <SelectTrigger className="w-full h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {REGION_OPTIONS.map((r) => (
                    <SelectItem
                      key={r.value}
                      value={r.value}
                      className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                    >
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                Environment
              </label>
              <Select value={environment} onValueChange={onEnvironmentChange}>
                <SelectTrigger className="w-full h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {environmentOptions.map((opt) => (
                    <SelectItem
                      key={opt.value}
                      value={opt.value}
                      className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                    >
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {environmentHelpText ? (
                <p className="text-[10px] text-[var(--text-secondary)]">
                  {environmentHelpText}
                </p>
              ) : null}
            </div>
          </div>

          {/* ── Error / success (shared) ── */}
          {connectionError && (
            <p className="text-xs text-red-500 flex items-start gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {connectionError}
            </p>
          )}
          {connectionSuccess && (
            <p className="text-xs text-[#10b981] flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              Successfully connected! Redirecting...
            </p>
          )}
          </div>
        </Tabs>

        {/* ── Footer ── */}
        <div className="flex gap-2 pt-4 border-t border-[var(--border-color)]">
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isConnecting}
            className="flex-1 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            Cancel
          </Button>
          <Button
            onClick={handlePrimaryAction}
            disabled={isPrimaryDisabled}
            className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            {primaryLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
