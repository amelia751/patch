"use client";

import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
import { useAuth } from "@/lib/auth-context";
import { UserAvatar } from "@/components/interface/shared/user-avatar";
import mockInfo from "./mock-aws/mock-info.json";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Cloud,
  Plus,
  ChevronDown,
  Settings,
  ArrowRight,
  FolderOpen,
  Moon,
  Sun,
  Github,
  User,
  Users,
  Bell,
  Shield,
  CreditCard,
  Palette,
  Key,
  Trash2,
  Check,
  Globe,
  Star,
  Lock,
  Copy,
  GitBranch,
  Sparkles,
  Zap,
  LogOut,
  Building,
  UserPlus,
  Mail,
  Crown,
  MoreHorizontal,
  Slack,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

// Auth components (modularized)
import {
  SignInDialog,
  SignUpDialog,
  EmailVerificationDialog,
  UserSettingsDialog,
  ForgotPasswordDialog,
  ResetPasswordDialog,
} from "@/components/interface/auth";
import { useUnauthenticatedAuthFlow } from "@/components/interface/auth/use-unauthenticated-auth-flow";

// Organization components (modularized)
import {
  type OrganizationData,
  CreateTeamDialog,
  InviteMemberDialog,
  OrganizationSettingsDialog,
  OrganizationSwitcher as OrganizationSwitcherComponent,
} from "@/components/interface/organization";

// Project components (modularized)
import {
  ProjectSettingsDialog,
  GitHubImportDialog,
  LinkGitHubDialog,
  ProjectSwitcher as ProjectSwitcherComponent,
} from "@/components/interface/project";

// Notification component
import { NotificationCenter } from "@/components/interface/shared/notifications";

interface HeaderProps {
  className?: string;
}

// Import mock data from JSON
const mockUser = mockInfo.mockUser;
const defaultOrganization: OrganizationData = mockInfo.defaultOrganization as OrganizationData;
const mockProjects = mockInfo.mockProjects;
const mockGitHubRepos = mockInfo.mockGitHubRepos;

// ============================================================================
// Organization Switcher Component (Left Breadcrumb)
// ============================================================================
function OrganizationSwitcher() {
  const [showOrgSettings, setShowOrgSettings] = useState(false);
  const [showCreateTeam, setShowCreateTeam] = useState(false);
  const [organization, setOrganization] = useState<OrganizationData>(defaultOrganization);
  const [orgCount, setOrgCount] = useState(1);
  const { isAuthenticated } = useAuth();

  // Fetch organization from API when authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      setOrganization(defaultOrganization);
      setOrgCount(1);
      return;
    }

    const fetchOrganization = async () => {
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

        // Fetch current organization
        const response = await fetch(`${API_URL}/api/organizations/current`, {
          credentials: "include",
        });

        if (response.ok) {
          const data = await response.json();
          setOrganization({
            id: data.id,
            name: data.name,
            slug: data.slug,
            type: data.type,
            role: data.role,
          });
        }

        // Fetch all organizations to get count
        const allOrgsResponse = await fetch(`${API_URL}/api/organizations`, {
          credentials: "include",
        });

        if (allOrgsResponse.ok) {
          const allOrgs = await allOrgsResponse.json();
          setOrgCount(allOrgs.length);
        }
      } catch (error) {
        console.error("Failed to fetch organization:", error);
      }
    };

    fetchOrganization();
  }, [isAuthenticated]);

  return (
    <>
      <OrganizationSwitcherComponent
        organization={organization}
        onShowOrgSettings={() => setShowOrgSettings(true)}
        onShowCreateTeam={() => setShowCreateTeam(true)}
      />

      <OrganizationSettingsDialog
        open={showOrgSettings}
        onOpenChange={setShowOrgSettings}
        organization={organization}
        orgCount={orgCount}
      />
      <CreateTeamDialog open={showCreateTeam} onOpenChange={setShowCreateTeam} />
    </>
  );
}

// ============================================================================
// User Account Menu (Right Side)
// ============================================================================
function UnauthenticatedUserMenu() {
  const flow = useUnauthenticatedAuthFlow();

  return (
    <>
      <button
        type="button"
        onClick={() => flow.setShowSignIn(true)}
        className="px-3 py-1.5 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
      >
        Sign In
      </button>
      <SignInDialog
        open={flow.showSignIn}
        onOpenChange={flow.onSignInOpenChange}
        onSignIn={flow.handleEmailSignIn}
        onGitHubSignIn={flow.handleGitHubSignIn}
        onGoogleSignIn={flow.handleGoogleSignIn}
        onShowSignUp={flow.handleShowSignUp}
        onShowForgotPassword={flow.handleShowForgotPassword}
        isSubmitting={flow.isSubmitting}
        error={flow.authError}
      />
      <SignUpDialog
        open={flow.showSignUp}
        onOpenChange={flow.onSignUpOpenChange}
        onSignUp={flow.handleSignUp}
        onGitHubSignUp={flow.handleGitHubSignIn}
        onGoogleSignUp={flow.handleGoogleSignIn}
        onShowSignIn={flow.handleShowSignIn}
        isSubmitting={flow.isSubmitting}
        error={flow.authError}
      />
      <EmailVerificationDialog
        open={flow.showVerification}
        onOpenChange={flow.setShowVerification}
        onVerify={flow.handleVerify}
        onResend={flow.handleResendCode}
        email={flow.pendingEmail}
        isSubmitting={flow.isSubmitting}
      />
      <ForgotPasswordDialog
        open={flow.showForgotPassword}
        onOpenChange={flow.setShowForgotPassword}
        onSubmit={flow.handleForgotPassword}
        onShowSignIn={flow.handleShowSignIn}
        isSubmitting={flow.isSubmitting}
      />
      <ResetPasswordDialog
        open={flow.showResetPassword}
        onOpenChange={flow.setShowResetPassword}
        onSubmit={flow.handleResetPassword}
        onResend={flow.handleResendResetCode}
        email={flow.pendingEmail}
        isSubmitting={flow.isSubmitting}
      />
    </>
  );
}

function UserAccountMenu() {
  const [showAccountSettings, setShowAccountSettings] = useState(false);
  const { user, isAuthenticated, logout } = useAuth();

  const handleSignOut = async () => {
    await logout();
  };

  // Get display info from user or fallback
  const displayName = user?.display_name || mockUser.name;
  const displayEmail = user?.email || mockUser.email;
  const avatarUrl = user?.avatar_url;

  if (!isAuthenticated) {
    return <UnauthenticatedUserMenu />;
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex items-center space-x-2 px-2 py-1.5 rounded-md hover:bg-[var(--bg-tertiary)] transition-colors">
            <div className="h-6 w-6 flex-shrink-0 rounded-full overflow-hidden">
              <UserAvatar src={avatarUrl} name={displayName} />
            </div>
            <span className="text-xs font-medium text-[var(--text-primary)] truncate">
              {displayName}
            </span>
            <ChevronDown className="h-3 w-3 text-[var(--text-secondary)]" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56 bg-[var(--bg-primary)] border-[var(--border-color)]">
          {/* User Info */}
          <div className="flex items-center space-x-2 p-2">
            <div className="h-8 w-8 rounded-full overflow-hidden flex-shrink-0">
              <UserAvatar src={avatarUrl} name={displayName} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-[var(--text-primary)] truncate">
                {displayName}
              </div>
              <div className="text-[10px] text-[var(--text-secondary)] truncate">{displayEmail}</div>
            </div>
          </div>

          <DropdownMenuSeparator className="bg-[var(--border-color)]" />

          {/* Manage Account */}
          <DropdownMenuItem
            onClick={() => setShowAccountSettings(true)}
            className="flex items-center space-x-2 p-2 cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
          >
            <User className="h-4 w-4 text-[var(--text-secondary)]" />
            <span className="text-xs text-[var(--text-primary)]">Manage Account</span>
          </DropdownMenuItem>

          <DropdownMenuSeparator className="bg-[var(--border-color)]" />

          {/* Sign Out */}
          <DropdownMenuItem
            onClick={handleSignOut}
            className="flex items-center space-x-2 p-2 cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
          >
            <LogOut className="h-4 w-4 text-[var(--text-secondary)]" />
            <span className="text-xs text-[var(--text-primary)]">Sign Out</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <UserSettingsDialog open={showAccountSettings} onOpenChange={setShowAccountSettings} />
    </>
  );
}

// ============================================================================
// Project Switcher Component
// ============================================================================
function ProjectSwitcher() {
  return <ProjectSwitcherComponent />;
}

// ============================================================================
// Email Verification Banner
// ============================================================================
function EmailVerificationBanner() {
  const { user, resendVerificationCode, verifyEmail } = useAuth();
  const [isResending, setIsResending] = useState(false);
  const [showVerifyDialog, setShowVerifyDialog] = useState(false);
  const [digits, setDigits] = useState(["", "", "", "", "", ""]);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState(false);

  // Don't show if user is verified, not logged in, or dismissed
  if (!user || user.email_verified || dismissed) {
    return null;
  }

  const handleResend = async () => {
    setIsResending(true);
    try {
      await resendVerificationCode(user.email);
      setShowVerifyDialog(true);
    } catch (err: any) {
      console.error("Failed to send verification code:", err);
    } finally {
      setIsResending(false);
    }
  };

  const handleDigitChange = (index: number, value: string) => {
    if (value.length > 1) value = value.slice(-1);
    if (!/^\d*$/.test(value)) return;
    
    const newDigits = [...digits];
    newDigits[index] = value;
    setDigits(newDigits);
    
    // Auto-focus next input
    if (value && index < 5) {
      const nextInput = document.getElementById(`digit-${index + 1}`);
      nextInput?.focus();
    }
  };

  const handleDigitKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      const prevInput = document.getElementById(`digit-${index - 1}`);
      prevInput?.focus();
    }
  };

  const handleDigitPaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const paste = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    const newDigits = [...digits];
    for (let i = 0; i < paste.length; i++) {
      newDigits[i] = paste[i];
    }
    setDigits(newDigits);
  };

  const handleVerify = async () => {
    const code = digits.join("");
    if (code.length !== 6) return;
    setIsVerifying(true);
    setError("");
    try {
      await verifyEmail(user.email, code);
      setShowVerifyDialog(false);
      // Force reload to update user state
      window.location.reload();
    } catch (err: any) {
      setError(err.message || "Invalid verification code");
      setDigits(["", "", "", "", "", ""]);
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <>
      <div className="bg-amber-500/10 dark:bg-amber-500/5 border-b border-[var(--border-color)] px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
          <Mail className="h-4 w-4" />
          <span className="text-xs font-medium">
            Please verify your email address ({user.email}) to access all features.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleResend}
            disabled={isResending}
            className="h-6 text-xs text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 dark:hover:bg-amber-500/10"
          >
            {isResending ? (
              <>
                <Spinner className="h-3 w-3 mr-1" />
                Sending...
              </>
            ) : (
              "Send verification code"
            )}
          </Button>
          <button
            onClick={() => setDismissed(true)}
            className="text-amber-700/60 dark:text-amber-300/60 hover:text-amber-700 dark:hover:text-amber-300 transition-colors"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Verification Code Dialog */}
      <Dialog open={showVerifyDialog} onOpenChange={setShowVerifyDialog}>
        <DialogContent className="sm:max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
          <DialogHeader>
            <DialogTitle className="text-[var(--text-primary)]">Enter Verification Code</DialogTitle>
            <DialogDescription className="text-[var(--text-secondary)]">
              We sent a 6-digit code to {user.email}. Check your inbox (and spam folder).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label className="text-[var(--text-primary)]">Verification Code</Label>
              <div className="flex justify-center gap-2">
                {digits.map((digit, index) => (
                  <input
                    key={index}
                    id={`digit-${index}`}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleDigitChange(index, e.target.value)}
                    onKeyDown={(e) => handleDigitKeyDown(index, e)}
                    onPaste={handleDigitPaste}
                    className="w-10 h-12 text-center text-xl font-semibold bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md text-[var(--text-primary)] focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors"
                  />
                ))}
              </div>
            </div>
            {error && (
              <p className="text-xs text-red-500 text-center">{error}</p>
            )}
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowVerifyDialog(false);
                  setDigits(["", "", "", "", "", ""]);
                  setError("");
                }}
                className="flex-1 border-[var(--border-color)] text-[var(--text-primary)]"
              >
                Cancel
              </Button>
              <Button
                onClick={handleVerify}
                disabled={isVerifying || digits.join("").length !== 6}
                className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                {isVerifying ? (
                  <>
                    <Spinner className="h-4 w-4 mr-2" />
                    Verifying...
                  </>
                ) : (
                  "Verify Email"
                )}
              </Button>
            </div>
            <p className="text-xs text-[var(--text-secondary)] text-center">
              Didn&apos;t receive the code?{" "}
              <button
                onClick={handleResend}
                disabled={isResending}
                className="text-primary hover:underline"
              >
                Resend
              </button>
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ============================================================================
// Header Component
// ============================================================================
export function Header({ className }: HeaderProps) {
  const { theme, toggleTheme } = useTheme();
  const { isAuthenticated, user } = useAuth();
  const [showLinkGitHub, setShowLinkGitHub] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Prevent hydration errors by waiting for client mount
  useEffect(() => {
    setMounted(true);
  }, []);

  // Check if user has GitHub App installed (for repo access)
  // Note: github_id/github_username is just OAuth login, github_app_installed means we can access repos
  const isGitHubLinked = user?.github_app_installed ?? false;

  const handleGitHubClick = () => {
    if (!isGitHubLinked && isAuthenticated) {
      setShowLinkGitHub(true);
    }
    // If linked, could open GitHub settings or nothing for now
  };

  return (
    <div className="flex flex-col">
      {/* Email verification banner - shows above header when email not verified */}
      <EmailVerificationBanner />
      
      <header className={cn(
        "flex items-center justify-between px-4 py-2 bg-[var(--bg-primary)] border-b border-[var(--border-color)] transition-colors",
        className
      )}>
      {/* Left side - Breadcrumb: Organization / Project */}
      <div className="flex items-center">
        <Breadcrumb>
          <BreadcrumbList className="gap-1">
            <BreadcrumbItem>
              <OrganizationSwitcher />
            </BreadcrumbItem>
            <BreadcrumbSeparator className="text-[var(--text-secondary)]">
              /
            </BreadcrumbSeparator>
            <BreadcrumbItem>
              <ProjectSwitcher />
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        </div>

      {/* Right side - GitHub, Slack, Notifications, Theme & User Account */}
      <div className="flex items-center space-x-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={handleGitHubClick}
                className={cn(
                  "p-1.5 rounded-md transition-colors border",
                  isGitHubLinked
                    ? "text-[#10b981] border-[#10b981]/30 hover:bg-[#10b981]/10"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] border-[var(--border-color)]"
                )}
              >
                <Github className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <p className="text-xs">
                {isGitHubLinked
                  ? `Connected as @${user?.github_username}`
                  : isAuthenticated
                    ? "Click to link GitHub"
                    : "GitHub"
                }
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
              >
                <Slack className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <p className="text-xs">Slack integration</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* Notification Center */}
        <NotificationCenter />

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleTheme}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)]"
              >
                {!mounted ? (
                  <Sun className="h-4 w-4" />
                ) : theme === "dark" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <p className="text-xs">Toggle {!mounted ? "theme" : theme === "dark" ? "light" : "dark"} mode</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <UserAccountMenu />
      </div>
    </header>

    {/* Link GitHub Dialog - shown when clicking GitHub icon when not linked */}
    <LinkGitHubDialog open={showLinkGitHub} onOpenChange={setShowLinkGitHub} />
    </div>
  );
}

export default Header;
