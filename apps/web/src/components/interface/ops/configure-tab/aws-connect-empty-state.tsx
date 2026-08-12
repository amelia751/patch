"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "@/lib/theme-context";
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
import {
  Shield,
  Key,
  Building2,
  CheckCircle2,
  ExternalLink,
  Copy,
  Check,
  ChevronRight,
  AlertTriangle,
  Cable,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AWSConnectEmptyStateProps {
  onConnect?: () => void;
  userId?: string;
  externalId?: string;
}

export function AWSConnectEmptyState({ onConnect, userId = "default", externalId: initialExternalId }: AWSConnectEmptyStateProps) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [showIAMDialog, setShowIAMDialog] = useState(false);
  const [showAccessKeysDialog, setShowAccessKeysDialog] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState("us-east-1");
  
  // Backend data
  const [externalId, setExternalId] = useState<string>("");
  const [cloudFormationUrl, setCloudFormationUrl] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [roleArn, setRoleArn] = useState("");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connectionSuccess, setConnectionSuccess] = useState(false);
  

  const ingressAccountId = "093955289594";

  useEffect(() => {
    setMounted(true);
  }, []);

  // Set initial external ID if provided
  useEffect(() => {
    if (initialExternalId && !externalId) {
      setExternalId(initialExternalId);
    }
  }, [initialExternalId]);

  // Fetch CloudFormation URL and external ID when dialog opens
  useEffect(() => {
    if (showIAMDialog && !externalId) {
      fetchCloudFormationUrl();
    }
  }, [showIAMDialog]);

  const fetchCloudFormationUrl = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `${API_URL}/api/aws/cloudformation-setup-url?region=${selectedRegion}&user_id=${userId}`,
        { credentials: "include" }
      );
      if (response.ok) {
        const data = await response.json();
        setExternalId(data.external_id);
        setCloudFormationUrl(data.url);
      }
    } catch (error) {
      console.error("Failed to fetch CloudFormation URL:", error);
      // Fallback to static values if backend not available
      const fallbackExternalId = initialExternalId || "ext-" + Math.random().toString(36).substring(2, 10);
      setExternalId(fallbackExternalId);
      setCloudFormationUrl(
        `https://console.aws.amazon.com/cloudformation/home?region=${selectedRegion}#/stacks/quickcreate?templateURL=https://cloud-infra-setup-resources.s3.amazonaws.com/aws/deployment-role.yaml&param_ExternalId=${fallbackExternalId}&param_IngressAccountId=${ingressAccountId}&stackName=DeploymentRole`
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleConnect = async () => {
    if (!roleArn.trim()) {
      setConnectionError("Please enter a valid IAM Role ARN");
      return;
    }

    if (!roleArn.startsWith("arn:aws:iam::")) {
      setConnectionError("Invalid ARN format. Expected: arn:aws:iam::ACCOUNT_ID:role/ROLE_NAME");
      return;
    }

    setIsConnecting(true);
    setConnectionError(null);

    try {
      // Validate and connect
      const response = await fetch(`${API_URL}/api/aws/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          role_arn: roleArn,
          external_id: externalId,
          user_id: userId,
          region: selectedRegion,
        }),
      });

      const data = await response.json();

      if (response.ok && data.connected) {
        setConnectionSuccess(true);
        setTimeout(() => {
          setShowIAMDialog(false);
          onConnect?.();
        }, 1500);
      } else {
        setConnectionError(data.detail || data.error || "Failed to connect");
      }
    } catch (error) {
      setConnectionError("Network error. Please check if the backend is running.");
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <>
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center max-w-md">
          <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
            <img
              src={mounted && theme === "dark" ? "/aws-dark.svg" : "/aws-light.svg"}
              alt="AWS"
              className="h-6 w-6"
            />
          </div>
          <h2 className="text-lg font-medium text-[var(--text-primary)] mb-2">
            Connect your AWS account
          </h2>
          <p className="text-sm text-[var(--text-secondary)] mb-6">
            Connect AWS to deploy and manage your infrastructure
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button
              onClick={() => setShowIAMDialog(true)}
              className="bg-primary hover:bg-primary/90 text-white"
            >
              <Cable className="h-4 w-4 mr-2" />
              Connect with IAM Role
            </Button>
          </div>
        </div>
      </div>

      {/* IAM Role Setup Dialog */}
      <Dialog open={showIAMDialog} onOpenChange={(open) => {
        setShowIAMDialog(open);
        if (!open) {
          setConnectionError(null);
          setConnectionSuccess(false);
        }
      }}>
        <DialogContent className="sm:max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] max-h-[90vh] overflow-y-auto">
          <DialogHeader className="mt-3">
            <DialogTitle className="text-sm font-medium text-[var(--text-primary)]">
              Connect via IAM Role
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)]">
              Set up secure access using an IAM role with tag-based permissions
            </DialogDescription>
            
            {/* Security Note */}
            <div className="mt-3 p-2.5 bg-primary/10 border border-primary/20 rounded-lg">
              <div className="text-[10px] text-[var(--text-secondary)]">
                <span className="font-medium text-primary">Tag-based security:</span> The agent can only manage resources tagged with{' '}
                <code className="px-1 py-0.5 bg-[var(--bg-tertiary)] rounded text-[9px]">ManagedBy=platform</code>.
                Your existing AWS resources remain untouched.
              </div>
            </div>
          </DialogHeader>

          <div className="space-y-6 py-4">
          
            {/* OPTION 1: CloudFormation */}
            <div className="border border-primary/30 rounded-lg p-4 bg-primary/5">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="text-sm font-medium text-[var(--text-primary)]">
                  Option 1: CloudFormation
                </h3>
                <span className={cn(
                  "text-[9px] px-2 py-0.5 rounded-full font-medium",
                  mounted && theme === "dark" && "bg-transparent text-primary border border-primary/30",
                  mounted && theme === "light" && "bg-primary text-white"
                )}>
                  Recommended
                </span>
              </div>

              {/* Step 1 */}
              <div className="space-y-3 mb-4">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-primary text-white text-[10px] font-bold flex items-center justify-center">
                    1
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Launch CloudFormation Stack
                  </h4>
                </div>
                <p className="text-xs text-[var(--text-secondary)] ml-7">
                  Click the button below to automatically create the IAM role in your AWS account.
                </p>
                <Button
                  onClick={() => {
                    const url = cloudFormationUrl || 
                      `https://console.aws.amazon.com/cloudformation/home?region=${selectedRegion}#/stacks/quickcreate?templateURL=https://cloud-infra-setup-resources.s3.amazonaws.com/aws/deployment-role.yaml&param_ExternalId=${externalId}&param_IngressAccountId=${ingressAccountId}&stackName=DeploymentRole`;
                    window.open(url, '_blank');
                  }}
                  disabled={isLoading || !externalId}
                  className="ml-7 bg-primary hover:bg-primary/90 text-white h-8 text-xs"
                >
                  {isLoading ? (
                    <Spinner className="h-3.5 w-3.5 mr-2" />
                  ) : (
                    <ExternalLink className="h-3.5 w-3.5 mr-2" />
                  )}
                  Launch CloudFormation Stack
                </Button>
              </div>

              {/* Step 2 */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-primary text-white text-[10px] font-bold flex items-center justify-center">
                    2
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Copy Role ARN from Outputs
                  </h4>
                </div>
                <div className="ml-7 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <p className="text-[10px] text-[var(--text-secondary)] mb-2">
                    After stack shows CREATE_COMPLETE:
                  </p>
                  <ol className="text-[10px] text-[var(--text-primary)] space-y-1 list-decimal list-inside">
                    <li>Go to <span className="font-medium">Stacks → DeploymentRole</span></li>
                    <li>Click the <span className="font-medium">Outputs</span> tab</li>
                    <li>Copy the <span className="font-medium">RoleArn</span> value</li>
                  </ol>
                  <div className="mt-3 p-2 bg-[var(--bg-tertiary)] rounded border border-[var(--border-color)]">
                    <p className="text-[9px] text-[var(--text-secondary)] mb-1">Example ARN format:</p>
                    <code className="text-[9px] font-mono text-[var(--text-primary)]">
                      arn:aws:iam::123456789012:role/DeploymentRole
                    </code>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-[var(--border-color)]"></div>
              <span className="text-xs text-[var(--text-secondary)]">OR</span>
              <div className="flex-1 h-px bg-[var(--border-color)]"></div>
            </div>

            {/* OPTION 2: Manual Setup */}
            <div className="border border-[var(--border-color)] rounded-lg p-4">
              <h3 className="text-sm font-medium text-[var(--text-primary)] mb-4">
                Option 2: Manual Setup
              </h3>

              {/* Step 1: Create Role */}
              <div className="space-y-3 mb-3">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-bold flex items-center justify-center border border-[var(--border-color)]">
                    1
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Create Role with Trust Policy
                  </h4>
                </div>
                <div className="ml-7 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <p className="text-[10px] text-[var(--text-secondary)] mb-2">
                    Go to IAM Console → Roles → Create Role → Custom trust policy
                  </p>
                  <div className="relative">
                    <pre className="text-[9px] font-mono bg-[var(--bg-tertiary)] text-[var(--text-primary)] p-2 rounded border border-[var(--border-color)] overflow-x-auto">
{`{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::${ingressAccountId}:root"
    },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {
        "sts:ExternalId": "${externalId}"
      }
    }
  }]
}`}
                    </pre>
                    <button
                      onClick={() => handleCopy(JSON.stringify({
                        "Version": "2012-10-17",
                        "Statement": [{
                          "Effect": "Allow",
                          "Principal": { "AWS": `arn:aws:iam::${ingressAccountId}:root` },
                          "Action": "sts:AssumeRole",
                          "Condition": { "StringEquals": { "sts:ExternalId": externalId } }
                        }]
                      }, null, 2), 'trust-policy')}
                      className="absolute top-1 right-1 p-1 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                    >
                      {copiedField === 'trust-policy' ? (
                        <Check className="h-3 w-3" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Step 2: Attach Permissions */}
              <div className="space-y-3 mb-3">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-bold flex items-center justify-center border border-[var(--border-color)]">
                    2
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Create Inline Policy (Tag-based)
                  </h4>
                </div>
                <div className="ml-7 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <p className="text-[10px] text-[var(--text-secondary)] mb-2">
                    After creating the role, go to <span className="font-medium">Permissions</span> → <span className="font-medium">Add permissions</span> → <span className="font-medium">Create inline policy</span> → <span className="font-medium">JSON</span>
                  </p>
                  <p className="text-[9px] text-[var(--text-secondary)] mb-2">
                    Use the CloudFormation template as reference for tag-based policy, or use these AWS managed policies for quick setup:
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {['AWSLambda_FullAccess', 'AmazonAPIGatewayAdministrator', 'AmazonDynamoDBFullAccess', 'AmazonS3FullAccess', 'AmazonRDSFullAccess'].map(policy => (
                      <code key={policy} className="text-[9px] font-mono bg-[var(--bg-tertiary)] text-[var(--text-primary)] px-1.5 py-0.5 rounded border border-[var(--border-color)]">
                        {policy}
                      </code>
                    ))}
                  </div>
                  <p className="text-[8px] text-[var(--text-secondary)] mt-2 italic">
                    Note: Managed policies provide broad access. For production, we recommend using CloudFormation for tag-based least privilege.
                  </p>
                </div>
              </div>

              {/* Step 3: Name Role */}
              <div className="space-y-3 mb-3">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-bold flex items-center justify-center border border-[var(--border-color)]">
                    3
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Name Your Role
                  </h4>
                </div>
                <div className="ml-7 flex items-center gap-2">
                  <code className="text-[10px] font-mono bg-[var(--bg-secondary)] text-[var(--text-primary)] px-2 py-1 rounded border border-[var(--border-color)]">
                    DeploymentRole
                  </code>
                  <button
                    onClick={() => handleCopy('DeploymentRole', 'role-name')}
                    className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                  >
                    {copiedField === 'role-name' ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                </div>
              </div>

              {/* Step 4: Copy ARN */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-bold flex items-center justify-center border border-[var(--border-color)]">
                    4
                  </div>
                  <h4 className="text-xs font-medium text-[var(--text-primary)]">
                    Copy the Role ARN
                  </h4>
                </div>
                <div className="ml-7 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                  <p className="text-[10px] text-[var(--text-secondary)] mb-2">
                    After creating, go to the role summary and copy the ARN.
                  </p>
                  <div className="p-2 bg-[var(--bg-tertiary)] rounded border border-[var(--border-color)]">
                    <p className="text-[9px] text-[var(--text-secondary)] mb-1">Example ARN format:</p>
                    <code className="text-[9px] font-mono text-[var(--text-primary)]">
                      arn:aws:iam::123456789012:role/DeploymentRole
                    </code>
                  </div>
                </div>
              </div>
            </div>

            {/* ARN Input */}
            <div className="space-y-2 pt-4 border-t border-[var(--border-color)]">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                Paste your IAM Role ARN
              </label>
              <input
                type="text"
                value={roleArn}
                onChange={(e) => {
                  setRoleArn(e.target.value);
                  setConnectionError(null);
                }}
                placeholder="arn:aws:iam::123456789012:role/DeploymentRole"
                className={cn(
                  "w-full px-3 py-2 text-xs font-mono bg-[var(--bg-secondary)] border rounded-md text-[var(--text-primary)] focus:outline-none focus:ring-2",
                  connectionError
                    ? "border-red-500 focus:ring-red-500"
                    : connectionSuccess
                    ? "border-primary focus:ring-[#2d9d9b]"
                    : "border-[var(--border-color)] focus:ring-[#2d9d9b]"
                )}
              />
              
              {/* ARN Validation Rules */}
              {roleArn && !connectionSuccess && !connectionError && (
                <div className="space-y-1.5 mt-2">
                  <ArnValidationRule 
                    valid={roleArn.startsWith("arn:aws:iam::")} 
                    text="Starts with arn:aws:iam::" 
                  />
                  <ArnValidationRule 
                    valid={/arn:aws:iam::\d{12}:/.test(roleArn)} 
                    text="Contains 12-digit AWS account ID" 
                  />
                  <ArnValidationRule 
                    valid={roleArn.includes(":role/")} 
                    text="Contains :role/ path" 
                  />
                  <ArnValidationRule 
                    valid={/role\/[A-Za-z0-9_+=,.@-]+$/.test(roleArn)} 
                    text="Has valid role name" 
                  />
                </div>
              )}
              
              {connectionError && (
                <p className="text-xs text-red-500 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {connectionError}
                </p>
              )}
              {connectionSuccess && (
                <p className="text-xs text-[#10b981] flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  Successfully connected! Redirecting...
                </p>
              )}
            </div>
          </div>

          <div className="flex gap-2 pt-4 border-t border-[var(--border-color)]">
            <Button
              variant="outline"
              onClick={() => {
                setShowIAMDialog(false);
                setConnectionError(null);
                setConnectionSuccess(false);
              }}
              disabled={isConnecting}
              className="flex-1 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            >
              Cancel
            </Button>
            <Button
              onClick={handleConnect}
              disabled={isConnecting || !roleArn.trim() || connectionSuccess}
              className="flex-1 bg-primary hover:bg-primary/90 text-white"
            >
              {isConnecting ? (
                <>
                  <Spinner className="h-4 w-4 mr-2" />
                  <span className="shimmer-text">Validating</span>
                </>
              ) : connectionSuccess ? (
                <>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  Connected!
                </>
              ) : (
                "Connect AWS Account"
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Access Keys Setup Dialog */}
      <Dialog open={showAccessKeysDialog} onOpenChange={setShowAccessKeysDialog}>
        <DialogContent className="sm:max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
          <DialogHeader>
            <DialogTitle className="text-[var(--text-primary)]">
              Connect via Access Keys
            </DialogTitle>
            <DialogDescription className="text-[var(--text-secondary)]">
              For development and testing purposes only
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Warning */}
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs text-amber-600 dark:text-amber-400 font-medium mb-1">
                    Not recommended for production
                  </p>
                  <p className="text-xs text-amber-600/80 dark:text-amber-400/80">
                    Access keys are encrypted but stored. Use IAM roles for production workloads.
                  </p>
                </div>
              </div>
            </div>

            {/* Access Key Input */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                AWS Access Key ID
              </label>
              <input
                type="text"
                placeholder="AKIAIOSFODNN7EXAMPLE"
                className="w-full px-3 py-2 text-xs bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>

            {/* Secret Key Input */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                AWS Secret Access Key
              </label>
              <input
                type="password"
                placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                className="w-full px-3 py-2 text-xs bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>

            {/* Region Input */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-primary)]">
                Default Region
              </label>
              <Select value={selectedRegion} onValueChange={setSelectedRegion}>
                <SelectTrigger className="w-full h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  <SelectItem value="us-east-1" className="text-xs">us-east-1</SelectItem>
                  <SelectItem value="us-west-2" className="text-xs">us-west-2</SelectItem>
                  <SelectItem value="eu-west-1" className="text-xs">eu-west-1</SelectItem>
                  <SelectItem value="ap-southeast-1" className="text-xs">ap-southeast-1</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex gap-2 pt-4 border-t border-[var(--border-color)]">
            <Button
              variant="outline"
              onClick={() => setShowAccessKeysDialog(false)}
              className="flex-1 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                setShowAccessKeysDialog(false);
                onConnect?.();
              }}
              className="flex-1 bg-amber-500 hover:bg-amber-500/90 text-white"
            >
              Connect
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ARN Validation Rule Component
function ArnValidationRule({ valid, text }: { valid: boolean; text: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <div className={cn("h-1.5 w-1.5 rounded-full", valid ? "bg-[#10b981]" : "bg-[var(--text-secondary)]")} />
      <span className={cn(valid ? "text-[#10b981]" : "text-[var(--text-secondary)]")}>{text}</span>
    </div>
  );
}
