"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { CheckCircle2, ExternalLink, AlertTriangle, Check } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

interface EnvironmentConnection {
  environment: string;
  accountId: string;
  roleArn: string;
  region: string;
  connectedAt: string;
  isDefault?: boolean;
}

interface AddEnvironmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (connection: EnvironmentConnection) => void;
  existingConnections: EnvironmentConnection[];
}

export function AddEnvironmentDialog({
  open,
  onOpenChange,
  onAdd,
  existingConnections,
}: AddEnvironmentDialogProps) {
  const [step, setStep] = useState<"select-env" | "select-account" | "connect">("select-env");
  const [selectedEnvironment, setSelectedEnvironment] = useState<string>("");
  const [accountType, setAccountType] = useState<"same" | "different">("same");
  const [roleArn, setRoleArn] = useState("");
  const [accountId, setAccountId] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionSuccess, setConnectionSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Get default connection
  const defaultConnection = existingConnections.find((c) => c.isDefault);

  // Get available environments
  const allEnvironments = ["dev", "staging", "prod"];
  const usedEnvironments = existingConnections
    .filter((c) => !c.isDefault)
    .map((c) => c.environment);
  const availableEnvironments = allEnvironments.filter((e) => !usedEnvironments.includes(e));

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setStep("select-env");
        setSelectedEnvironment("");
        setAccountType("same");
        setRoleArn("");
        setAccountId("");
        setRegion("us-east-1");
        setIsConnecting(false);
        setConnectionSuccess(false);
        setError(null);
      }, 300);
    }
  }, [open]);

  // Pre-fill values when account type or environment changes
  useEffect(() => {
    if (accountType === "same" && defaultConnection) {
      setRoleArn(defaultConnection.roleArn);
      setAccountId(defaultConnection.accountId);
      setRegion(defaultConnection.region);
    } else if (accountType === "different") {
      setRoleArn("");
      setAccountId("");
    }
  }, [accountType, defaultConnection]);

  const handleNext = () => {
    if (step === "select-env") {
      if (!selectedEnvironment) {
        setError("Please select an environment");
        return;
      }
      setError(null);
      setStep("select-account");
    } else if (step === "select-account") {
      setError(null);
      setStep("connect");
    }
  };

  const handleBack = () => {
    setError(null);
    if (step === "connect") {
      setStep("select-account");
    } else if (step === "select-account") {
      setStep("select-env");
    }
  };

  const handleConnect = () => {
    if (!roleArn.trim()) {
      setError("Please enter a valid IAM Role ARN");
      return;
    }

    if (!roleArn.startsWith("arn:aws:iam::")) {
      setError("Invalid ARN format");
      return;
    }

    setIsConnecting(true);
    setError(null);

    // Simulate connection
    setTimeout(() => {
      setConnectionSuccess(true);
      setIsConnecting(false);

      // Extract account ID from ARN if not set
      const arnAccountId = roleArn.match(/arn:aws:iam::(\d{12}):/)?.[1] || accountId;

      setTimeout(() => {
        onAdd({
          environment: selectedEnvironment,
          accountId: arnAccountId,
          roleArn,
          region,
          connectedAt: new Date().toISOString(),
        });
        onOpenChange(false);
      }, 1000);
    }, 2000);
  };

  const getEnvironmentLabel = (env: string) => {
    if (env === "dev") return "Development";
    if (env === "staging") return "Staging";
    if (env === "prod") return "Production";
    return env;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] max-h-[90vh] overflow-y-auto">
        <DialogHeader className="mt-3">
          <DialogTitle className="text-sm font-medium text-[var(--text-primary)]">
            Add Environment Connection
          </DialogTitle>
          <DialogDescription className="text-xs text-[var(--text-secondary)]">
            {step === "select-env" && "Choose which environment to configure"}
            {step === "select-account" && "Choose whether to use the same AWS account or a different one"}
            {step === "connect" && "Connect the AWS account for this environment"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Step 1: Select Environment */}
          {step === "select-env" && (
            <div className="space-y-4">
              <div>
                <Label className="text-xs font-medium text-[var(--text-primary)] mb-2 block">
                  Environment
                </Label>
                <Select value={selectedEnvironment} onValueChange={setSelectedEnvironment}>
                  <SelectTrigger className="w-full h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors [&>span]:text-[var(--text-primary)]">
                    <SelectValue placeholder="Select an environment" />
                  </SelectTrigger>
                  <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)] z-50">
                    {availableEnvironments.map((env) => (
                      <SelectItem
                        key={env}
                        value={env}
                        className="text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)] cursor-pointer transition-colors"
                      >
                        {getEnvironmentLabel(env)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedEnvironment && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    You're adding a specific connection for <strong>{getEnvironmentLabel(selectedEnvironment)}</strong>.
                    This will override the default connection for this environment only.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Select Account Type */}
          {step === "select-account" && (
            <div className="space-y-4">
              <div className="space-y-3">
                {/* Same Account Option */}
                <button
                  onClick={() => setAccountType("same")}
                  className={cn(
                    "relative w-full p-4 border rounded-lg cursor-pointer transition-colors text-left",
                    accountType === "same"
                      ? "border-primary bg-primary/5"
                      : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                  )}
                >
                  {/* Checkmark for selected */}
                  {accountType === "same" && (
                    <div className="absolute top-2 right-2">
                      <Check className="h-4 w-4 text-primary" />
                    </div>
                  )}

                  <h3 className="text-sm font-medium text-[var(--text-primary)] mb-1">
                    Same AWS Account
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)] mb-2">
                    Use the same account ({defaultConnection?.accountId}) with logical separation via resource tagging
                  </p>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-[#10b981]/30 text-[#10b981]">
                      Simpler setup
                    </Badge>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-[#10b981]/30 text-[#10b981]">
                      Lower cost
                    </Badge>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-amber-500/30 text-amber-500">
                      Weaker isolation
                    </Badge>
                  </div>
                </button>

                {/* Different Account Option */}
                <button
                  onClick={() => setAccountType("different")}
                  className={cn(
                    "relative w-full p-4 border rounded-lg cursor-pointer transition-colors text-left",
                    accountType === "different"
                      ? "border-primary bg-primary/5"
                      : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                  )}
                >
                  {/* Checkmark for selected */}
                  {accountType === "different" && (
                    <div className="absolute top-2 right-2">
                      <Check className="h-4 w-4 text-primary" />
                    </div>
                  )}

                  <h3 className="text-sm font-medium text-[var(--text-primary)] mb-1">
                    Different AWS Account
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)] mb-2">
                    Use a separate AWS account for complete account-level isolation
                  </p>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-[#10b981]/30 text-[#10b981]">
                      Complete isolation
                    </Badge>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-[#10b981]/30 text-[#10b981]">
                      Best for prod
                    </Badge>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-amber-500/30 text-amber-500">
                      Requires setup
                    </Badge>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Connect */}
          {step === "connect" && (
            <div className="space-y-4">
              {accountType === "same" ? (
                <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg">
                  <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-3">
                    Using existing connection
                  </h4>
                  <div className="space-y-2">
                    <div>
                      <Label className="text-xs text-[var(--text-secondary)]">AWS Account</Label>
                      <p className="text-sm text-[var(--text-primary)] font-mono">{defaultConnection?.accountId}</p>
                    </div>
                    <div>
                      <Label className="text-xs text-[var(--text-secondary)]">IAM Role ARN</Label>
                      <p className="text-xs text-[var(--text-primary)] font-mono bg-[var(--bg-primary)] p-2 rounded border border-[var(--border-color)] mt-1">
                        {defaultConnection?.roleArn}
                      </p>
                    </div>
                    <div>
                      <Label className="text-xs text-[var(--text-secondary)]">Region</Label>
                      <p className="text-sm text-[var(--text-primary)]">{defaultConnection?.region}</p>
                    </div>
                  </div>
                  <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    <p className="text-[10px] text-amber-600 dark:text-amber-400">
                      Resources for <strong>{getEnvironmentLabel(selectedEnvironment)}</strong> will be tagged with{" "}
                      <code className="px-1 py-0.5 bg-[var(--bg-tertiary)] rounded text-[9px]">
                        Environment={selectedEnvironment}
                      </code>{" "}
                      to logically separate them from other environments.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      You'll need to set up CloudFormation in the new AWS account using the same external ID as your
                      default connection. This ensures consistent trust relationships.
                    </p>
                  </div>

                  <div>
                    <Label className="text-xs font-medium text-[var(--text-primary)] mb-2 block">
                      Region
                    </Label>
                    <Select value={region} onValueChange={setRegion}>
                      <SelectTrigger className="w-full h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors [&>span]:text-[var(--text-primary)]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)] z-50">
                        <SelectItem value="us-east-1" className="text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)] cursor-pointer transition-colors">us-east-1</SelectItem>
                        <SelectItem value="us-west-2" className="text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)] cursor-pointer transition-colors">us-west-2</SelectItem>
                        <SelectItem value="eu-west-1" className="text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)] cursor-pointer transition-colors">eu-west-1</SelectItem>
                        <SelectItem value="ap-southeast-1" className="text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)] cursor-pointer transition-colors">ap-southeast-1</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Button
                      onClick={() => {
                        window.open(
                          `https://console.aws.amazon.com/cloudformation/home?region=${region}#/stacks/quickcreate?templateURL=https://cloud-infra-setup-resources.s3.amazonaws.com/aws/deployment-role.yaml&stackName=DeploymentRole-${selectedEnvironment}`,
                          "_blank"
                        );
                      }}
                      className="w-full bg-primary hover:bg-primary/90 text-white h-8 text-xs transition-colors"
                    >
                      <ExternalLink className="h-3.5 w-3.5 mr-2" />
                      Launch CloudFormation Stack
                    </Button>
                    <p className="text-[10px] text-[var(--text-secondary)] mt-2">
                      After stack creation, copy the Role ARN from the Outputs tab
                    </p>
                  </div>

                  <div>
                    <Label className="text-xs font-medium text-[var(--text-primary)] mb-2 block">
                      IAM Role ARN
                    </Label>
                    <Input
                      type="text"
                      value={roleArn}
                      onChange={(e) => {
                        setRoleArn(e.target.value);
                        setError(null);
                      }}
                      placeholder="arn:aws:iam::987654321098:role/DeploymentRole"
                      className={cn(
                        "h-9 text-xs font-mono bg-[var(--bg-secondary)] text-[var(--text-primary)] transition-colors",
                        error
                          ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                          : "border-[var(--border-color)] focus:ring-[#2d9d9b] focus:border-primary"
                      )}
                    />
                  </div>
                </div>
              )}

              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <p className="text-xs text-red-600 dark:text-red-400 flex items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {error}
                  </p>
                </div>
              )}

              {connectionSuccess && (
                <div className="p-3 bg-[#10b981]/10 border border-[#10b981]/20 rounded-lg">
                  <p className="text-xs text-[#10b981] flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Successfully connected! Adding environment...
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-2 pt-4 border-t border-[var(--border-color)]">
          {step !== "select-env" && (
            <Button
              variant="outline"
              onClick={handleBack}
              disabled={isConnecting || connectionSuccess}
              className="border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-50"
            >
              Back
            </Button>
          )}
          <div className="flex-1" />
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isConnecting || connectionSuccess}
            className="border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-50"
          >
            Cancel
          </Button>
          {step === "connect" ? (
            <Button
              onClick={handleConnect}
              disabled={isConnecting || connectionSuccess || (accountType === "different" && !roleArn.trim())}
              className="bg-primary hover:bg-primary/90 text-white transition-colors disabled:opacity-50"
            >
              {isConnecting ? (
                <>
                  <Spinner className="h-4 w-4 mr-2" />
                  <span className="shimmer-text">Connecting</span>
                </>
              ) : connectionSuccess ? (
                <>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  Connected!
                </>
              ) : (
                "Connect"
              )}
            </Button>
          ) : (
            <Button
              onClick={handleNext}
              className="bg-primary hover:bg-primary/90 text-white transition-colors"
            >
              Next
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
