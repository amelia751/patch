"use client";

import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ChevronDown,
  Settings,
  Users,
  CreditCard,
  Trash2,
  Check,
  Building,
  UserPlus,
  Mail,
  MoreHorizontal,
  Orbit,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

// Types
export interface OrganizationData {
  id: string;
  name: string;
  slug: string;
  type: string;
  role?: string;
}

interface Member {
  user_id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  role: string;
  joined_at: string;
}

// ============================================================================
// Create Team Dialog
// ============================================================================
export function CreateTeamDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [emails, setEmails] = useState<string[]>([]);
  const [emailInput, setEmailInput] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && emailInput.trim()) {
      e.preventDefault();
      // Basic email validation
      const email = emailInput.trim();
      if (email.includes("@") && !emails.includes(email)) {
        setEmails([...emails, email]);
        setEmailInput("");
      }
    }
  };

  const removeEmail = (emailToRemove: string) => {
    setEmails(emails.filter(e => e !== emailToRemove));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <Users className="h-5 w-5 text-white" />
            </div>
          <div>
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Create a Team</DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)]">
                Collaborate on projects with others.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Team Name</Label>
            <Input placeholder="CloudCraft Studios" className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20" />
          </div>
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Team URL</Label>
            <div className="flex items-center">
              <span className="text-xs text-[var(--text-secondary)] px-3 py-2.5 bg-[var(--bg-tertiary)] border border-r-0 border-[var(--border-color)] rounded-l-md h-10 flex items-center">patchapi/</span>
              <Input placeholder="cloudcraft" className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] rounded-l-none focus:border-primary focus:ring-primary/20" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Invite Members (optional)</Label>
            <Input
              placeholder="email@example.com"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              onKeyDown={handleKeyDown}
              className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
            />
            <p className="text-[10px] text-[var(--text-secondary)]">Press Enter to add email</p>
            {emails.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {emails.map((email) => (
                  <div
                    key={email}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary/10 border border-primary/30 text-primary"
                  >
                    <span className="text-xs">{email}</span>
                    <button
                      type="button"
                      onClick={() => removeEmail(email)}
                      className="hover:bg-primary/20 rounded p-0.5 transition-colors"
                    >
                      <svg
                        className="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">Cancel</Button>
          <Button size="sm" className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm">Create Team</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Invite Member Dialog
// ============================================================================
export function InviteMemberDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "member" | "admin">("member");
  const [isInviting, setIsInviting] = useState(false);

  const roleConfig = {
    admin: { label: "Admin", description: "Manage members and settings" },
    member: { label: "Member", description: "View and edit projects" },
    viewer: { label: "Viewer", description: "Read-only access" },
  };

  const handleInvite = async () => {
    if (!email) return;

    setIsInviting(true);
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log("Inviting:", email, "as", role);
    setIsInviting(false);
    setEmail("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <UserPlus className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Invite Member</DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)]">
                Add a new member to your organization.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Email Address</Label>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="colleague@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="flex-1 h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
              />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    className="h-10 px-3 text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] min-w-[100px] justify-between"
                  >
                    {roleConfig[role].label}
                    <ChevronDown className="h-3 w-3 ml-2 text-[var(--text-secondary)]" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-[200px] bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {(Object.keys(roleConfig) as Array<keyof typeof roleConfig>).map((roleKey) => {
                    return (
                      <DropdownMenuItem
                        key={roleKey}
                        onClick={() => setRole(roleKey)}
                        className="cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
                      >
                        <div className="flex flex-col w-full">
                          <p className="text-xs font-medium text-[var(--text-primary)]">{roleConfig[roleKey].label}</p>
                          <p className="text-[10px] text-[var(--text-secondary)]">{roleConfig[roleKey].description}</p>
                        </div>
                      </DropdownMenuItem>
                    );
                  })}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <p className="text-[10px] text-[var(--text-secondary)]">
              {roleConfig[role].description}
            </p>
          </div>

          <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-color)]">
            <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
              An invitation email will be sent to {email || "the member"} with instructions to join your organization.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleInvite}
            disabled={!email || isInviting}
            className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isInviting ? (
              <>
                <Spinner className="h-3.5 w-3.5 mr-1.5" />
                Sending...
              </>
            ) : (
              <>
                <Mail className="h-3.5 w-3.5 mr-1.5" />
                Send Invite
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Upgrade Plan Dialog
// ============================================================================
export function UpgradePlanDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const plans = [
    {
      name: "Growth",
      price: "$49",
      description: "For growing teams and businesses",
      features: ["5 projects", "10 sandbox hours/month", "50 deployments/day", "Sandbox execution", "One-click deploy", "Dev & Staging environments", "GitHub PR integration"]
    },
    {
      name: "Enterprise",
      price: "Custom",
      description: "For large organizations",
      features: ["Unlimited projects", "Unlimited sandbox", "Unlimited deployments", "Production environment", "AWS Organizations", "Multi-account support", "SOC2/HIPAA compliance", "Dedicated support", "SLA"]
    }
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <Orbit className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Choose Your Plan</DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)]">
                Select the plan that best fits your needs
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 mt-4">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className="p-5 rounded-xl border-2 border-[var(--border-color)] bg-[var(--bg-secondary)]"
            >
              <div className="mb-4">
                <h3 className="text-base font-bold text-[var(--text-primary)] mb-1">{plan.name}</h3>
                <p className="text-[10px] text-[var(--text-secondary)] mb-3">{plan.description}</p>
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl text-[var(--text-primary)]">{plan.price}</span>
                  {plan.price !== "Custom" && (
                    <span className="text-xs text-[var(--text-secondary)]">/month</span>
                  )}
                </div>
              </div>

              <ul className="space-y-2 mb-5">
                {plan.features.map((feature, idx) => (
                  <li key={idx} className="text-xs text-[var(--text-primary)] flex items-start gap-2">
                    <Check className="h-3.5 w-3.5 text-[#10b981] shrink-0 mt-0.5" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                size="sm"
                className="w-full text-xs h-9 bg-primary hover:bg-primary-hover text-primary-foreground"
              >
                {plan.price === "Custom" ? "Contact Sales" : "Upgrade"}
              </Button>
            </div>
          ))}
        </div>

        {/* Additional Info */}
        <div className="mt-4 p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-color)]">
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            You can cancel your subscription at any time. Billing is monthly and you'll be charged immediately upon upgrading.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Organization Settings Dialog (Clerk-style)
// ============================================================================
export function OrganizationSettingsDialog({ open, onOpenChange, organization, orgCount }: { open: boolean; onOpenChange: (open: boolean) => void; organization: OrganizationData; orgCount: number }) {
  const [activeTab, setActiveTab] = useState("general");
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [showUpgradeDialog, setShowUpgradeDialog] = useState(false);
  const { theme} = useTheme();

  // Form state
  const [name, setName] = useState(organization.name);
  const [slug, setSlug] = useState(organization.slug);
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugChecking, setSlugChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Members state
  const [members, setMembers] = useState<Member[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Fetch real members when dialog opens and org exists
  useEffect(() => {
    if (!open || !organization.id) {
      setMembers([]);
      return;
    }

    const fetchMembers = async () => {
      setLoadingMembers(true);
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const response = await fetch(`${API_URL}/api/organizations/${organization.id}/members`, {
          credentials: "include",
        });

        if (response.ok) {
          const data = await response.json();
          setMembers(data.length > 0 ? data : []);
        } else {
          setMembers([]);
        }
      } catch (error) {
        console.error("Failed to fetch members:", error);
        setMembers([]);
      } finally {
        setLoadingMembers(false);
      }
    };

    fetchMembers();
  }, [open, organization.id]);

  // Reset form when organization changes
  useEffect(() => {
    setName(organization.name);
    setSlug(organization.slug);
    setSlugError(null);
  }, [organization]);

  // Debounced slug validation
  useEffect(() => {
    if (slug === organization.slug) {
      setSlugError(null);
      return;
    }

    const timer = setTimeout(async () => {
      if (slug.length < 3) {
        setSlugError("Slug must be at least 3 characters");
        return;
      }

      // Check format
      if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(slug) && slug.length > 2) {
        setSlugError("Slug must start and end with a letter or number");
        return;
      }

      if (/--/.test(slug)) {
        setSlugError("Slug cannot contain consecutive hyphens");
        return;
      }

      setSlugChecking(true);
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const response = await fetch(`${API_URL}/api/organizations/check-slug`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ slug }),
        });

        if (response.ok) {
          const data = await response.json();
          if (!data.available) {
            setSlugError(data.message || "This slug is already taken");
          } else {
            setSlugError(null);
          }
        }
      } catch (error) {
        console.error("Slug check failed:", error);
      } finally {
        setSlugChecking(false);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [slug, organization.slug]);

  // Save changes
  const handleSave = async () => {
    if (slugError || slugChecking) return;

    setIsSaving(true);
    setSaveSuccess(false);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/organizations/${organization.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: name !== organization.name ? name : undefined,
          slug: slug !== organization.slug ? slug : undefined,
        }),
      });

      if (response.ok) {
        setSaveSuccess(true);
        // Refresh the page to update the organization data
        setTimeout(() => window.location.reload(), 500);
      } else {
        const error = await response.json();
        setSlugError(error.detail || "Failed to save changes");
      }
    } catch (error) {
      console.error("Save failed:", error);
      setSlugError("Failed to save changes");
    } finally {
      setIsSaving(false);
    }
  };

  // Delete organization
  const handleDeleteOrganization = async () => {
    setIsDeleting(true);
    setDeleteError(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/organizations/${organization.id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to delete organization");
      }

      // Close dialog and refresh page to update org list
      onOpenChange(false);
      setTimeout(() => window.location.reload(), 300);
    } catch (err: any) {
      console.error("Error deleting organization:", err);
      setDeleteError(err.message || "Failed to delete organization");
    } finally {
      setIsDeleting(false);
    }
  };

  const hasChanges = name !== organization.name || slug !== organization.slug;

  const tabs = [
    { id: "general", label: "General", icon: Building },
    { id: "members", label: "Members", icon: Users },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "danger", label: "Danger Zone", icon: Trash2 },
  ];

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] p-0">
          <div className="flex h-[520px] pt-3">
          {/* Sidebar */}
          <div className="w-48 border-r border-[var(--border-color)] p-4 bg-[var(--bg-secondary)]/30">
            <DialogHeader className="mb-4">
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Organization</DialogTitle>
              <DialogDescription className="text-[10px] text-[var(--text-secondary)]">{organization.name}</DialogDescription>
            </DialogHeader>
            <nav className="space-y-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 text-xs rounded-lg transition-all duration-200",
                    activeTab === tab.id
                      ? tab.id === "danger" ? "bg-red-500 text-white shadow-sm" : "bg-primary text-primary-foreground shadow-sm"
                      : tab.id === "danger"
                        ? "text-red-500 hover:bg-red-500/10"
                        : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  )}
                >
                  <tab.icon className="h-3.5 w-3.5" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto">
            {activeTab === "general" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">General Settings</h3>

                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <Label className="text-xs text-[var(--text-secondary)]">Organization Name</Label>
                    <Input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label className="text-xs text-[var(--text-secondary)]">Organization Slug</Label>
                    <div className="flex items-center">
                      <span className="text-xs text-[var(--text-secondary)] px-3 py-2 bg-[var(--bg-tertiary)] border border-r-0 border-[var(--border-color)] rounded-l-md h-9 flex items-center">patchapi/</span>
                      <Input
                        value={slug}
                        onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                        className={cn(
                          "h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] rounded-l-none focus:border-primary focus:ring-primary/20",
                          slugError && "border-red-500 focus:border-red-500"
                        )}
                      />
                    </div>
                    {slugChecking && (
                      <p className="text-[10px] text-[var(--text-secondary)] flex items-center gap-1">
                        <Spinner className="h-3 w-3" />
                        <span className="shimmer-text">Checking availability</span>
                      </p>
                    )}
                    {slugError && !slugChecking && (
                      <p className="text-[10px] text-red-500">{slugError}</p>
                    )}
                    {!slugError && !slugChecking && slug !== organization.slug && slug.length >= 3 && (
                      <p className="text-[10px] text-[#10b981] flex items-center gap-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#10b981]" />
                        Slug is available
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 border-t border-[var(--border-color)]">
                  {saveSuccess && (
                    <span className="text-xs text-[#10b981]">✓ Saved!</span>
                  )}
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={!hasChanges || !!slugError || slugChecking || isSaving}
                    className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSaving ? (
                      <>
                        <Spinner className="h-3 w-3 mr-1.5" />
                        Saving...
                      </>
                    ) : (
                      "Save Changes"
                    )}
                  </Button>
                </div>
              </div>
            )}

            {activeTab === "members" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between pt-2">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">Members</h3>
                  <Button
                    size="sm"
                    onClick={() => setShowInviteDialog(true)}
                    className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm"
                  >
                    <UserPlus className="h-3.5 w-3.5 mr-1.5" />
                    Invite
                  </Button>
                </div>

                {/* Pending Invitations */}
                <div className="p-3 rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)]/30">
                  <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                    <Mail className="h-4 w-4" />
                    <span>No pending invitations</span>
                  </div>
                </div>

                {/* Members List */}
                <div className="space-y-2">
                  {members.map((member) => (
                    <div key={member.user_id} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--bg-secondary)]/30 border border-[var(--border-color)]">
                      <div className="h-9 w-9 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-medium text-white">
                          {member.display_name.split(' ').map(n => n[0]).join('')}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-medium text-[var(--text-primary)] truncate">{member.display_name}</p>
                        </div>
                        <p className="text-[10px] text-[var(--text-secondary)] truncate">{member.email}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "text-[10px] px-2 py-0.5 rounded-full font-medium",
                          member.role === "owner" && theme === "dark" && "bg-transparent text-orange-500 border border-orange-500/30",
                          member.role === "owner" && theme === "light" && "bg-orange-500 text-white",
                          member.role === "admin" && theme === "dark" && "bg-transparent text-yellow-500 border border-yellow-500/30",
                          member.role === "admin" && theme === "light" && "bg-yellow-500 text-white",
                          member.role === "member" && theme === "dark" && "bg-transparent text-primary border border-primary/30",
                          member.role === "member" && theme === "light" && "bg-primary text-primary-foreground",
                          member.role === "viewer" && theme === "dark" && "bg-transparent text-[var(--text-secondary)] border border-[var(--border-color)]",
                          member.role === "viewer" && theme === "light" && "bg-gray-400 text-white"
                        )}>
                          {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                        </span>
                        {member.role !== "owner" && (
                          <button className="p-1 rounded hover:bg-[var(--bg-tertiary)]">
                            <MoreHorizontal className="h-4 w-4 text-[var(--text-secondary)]" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === "billing" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">Billing & Plan</h3>

                {/* Current Plan */}
                <div className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Orbit className="h-4 w-4 text-[var(--text-primary)]" />
                      <span className="text-sm font-semibold text-[var(--text-primary)]">Starter Plan</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-color)] font-medium">Current</span>
                  </div>
                  <div className="mb-4">
                    <span className="text-2xl text-[var(--text-primary)]">$0</span>
                    <span className="text-xs text-[var(--text-secondary)]">/month</span>
                  </div>
                  <ul className="space-y-2 mb-4">
                    <li className="text-xs text-[var(--text-primary)] flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-[#10b981]" /> 1 project
                    </li>
                    <li className="text-xs text-[var(--text-primary)] flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-[#10b981]" /> No sandbox access
                    </li>
                    <li className="text-xs text-[var(--text-primary)] flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-[#10b981]" /> 5 deployments per day
                    </li>
                  </ul>
                  <Button
                    size="sm"
                    onClick={() => setShowUpgradeDialog(true)}
                    className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm"
                  >
                    Upgrade Plan
                  </Button>
                </div>

                {/* Billing Info */}
                <div className="p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]">
                  <h4 className="text-xs font-medium text-[var(--text-primary)] mb-3">Payment Method</h4>
                  <p className="text-xs text-[var(--text-secondary)]">No payment method on file</p>
                  <Button variant="outline" size="sm" className="mt-3 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">
                    Add Payment Method
                  </Button>
                </div>
              </div>
            )}

            {activeTab === "danger" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-red-500">Danger Zone</h3>

                {/* Leave Organization */}
                {orgCount > 1 && organization.type !== "personal" && (
                  <div className="p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]/30">
                    <h4 className="text-xs font-medium text-[var(--text-primary)] mb-1">Leave Organization</h4>
                    <p className="text-[11px] text-[var(--text-secondary)] mb-3">You will lose access to all projects and data in this organization.</p>
                    <Button variant="outline" size="sm" className="text-xs border-red-500/30 text-red-500 hover:text-red-500 hover:bg-red-500/10">
                      Leave Organization
                    </Button>
                  </div>
                )}

                {/* Delete Organization */}
                <div className="p-5 rounded-xl border-2 border-red-500/20">
                  <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-2">Delete Organization</h4>
                  <p className="text-[11px] text-[var(--text-secondary)] mb-4 leading-relaxed">
                    {organization.type === "personal"
                      ? "Your personal organization cannot be deleted. It serves as your default workspace."
                      : orgCount <= 1
                      ? "You cannot delete your only organization. You must have at least one organization."
                      : "Permanently delete this organization and all associated projects. This action cannot be undone."}
                  </p>
                  {!showDeleteConfirm ? (
                    <Button
                      size="sm"
                      variant="destructive"
                      className="text-xs bg-red-500 hover:bg-red-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => setShowDeleteConfirm(true)}
                      disabled={organization.type === "personal" || orgCount <= 1}
                    >
                      Delete Organization
                    </Button>
                  ) : (
                    <div className="space-y-3 pt-2 border-t border-red-500/20">
                      <p className="text-[10px] text-[var(--text-secondary)]">
                        Type <strong className="text-red-500">{organization.name}</strong> to confirm deletion:
                      </p>
                      <Input
                        value={deleteConfirmText}
                        onChange={(e) => setDeleteConfirmText(e.target.value)}
                        placeholder="Type organization name to confirm"
                        className="h-9 text-sm bg-[var(--bg-secondary)] border-red-500/30 text-[var(--text-primary)] focus:border-red-500 focus:ring-red-500/20"
                      />
                      {deleteError && (
                        <p className="text-[10px] text-red-500">{deleteError}</p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                          onClick={() => {
                            setShowDeleteConfirm(false);
                            setDeleteConfirmText("");
                            setDeleteError(null);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          className="text-xs bg-red-500 hover:bg-red-600 text-white"
                          onClick={handleDeleteOrganization}
                          disabled={deleteConfirmText !== organization.name || isDeleting}
                        >
                          {isDeleting ? (
                            <>
                              <Spinner className="h-3 w-3 mr-1.5" />
                              <span className="shimmer-text">Deleting</span>
                            </>
                          ) : (
                            "Permanently Delete"
                          )}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
    <InviteMemberDialog open={showInviteDialog} onOpenChange={setShowInviteDialog} />
    <UpgradePlanDialog open={showUpgradeDialog} onOpenChange={setShowUpgradeDialog} />
    </>
  );
}

// ============================================================================
// Organization Switcher Component (to be used in header)
// ============================================================================
export function OrganizationSwitcher({
  organization,
  onShowOrgSettings,
  onShowCreateTeam
}: {
  organization: OrganizationData;
  onShowOrgSettings: () => void;
  onShowCreateTeam: () => void;
}) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Format type for display
  const displayType = organization.type.charAt(0).toUpperCase() + organization.type.slice(1);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center space-x-2 px-2 py-1.5 rounded-md hover:bg-[var(--bg-tertiary)] transition-colors">
          <div className={cn(
            "h-5 w-5 flex-shrink-0 rounded overflow-hidden flex items-center justify-center transition-colors",
            mounted && theme === "dark"
              ? "bg-primary/10"
              : "bg-gradient-to-br from-primary to-primary-strong"
          )}>
            <Building className={cn("h-3 w-3", mounted && theme === "dark" ? "text-primary" : "text-white")} />
          </div>
          <span className="text-xs font-medium text-[var(--text-primary)] truncate">
            {organization.name}
          </span>
          <ChevronDown className="h-3 w-3 text-[var(--text-secondary)]" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56 bg-[var(--bg-primary)] border-[var(--border-color)]">
        {/* Current Organization */}
        <div className="flex items-center space-x-2 p-2">
          <div className={cn(
            "h-6 w-6 rounded overflow-hidden flex items-center justify-center flex-shrink-0 transition-colors",
            mounted && theme === "dark"
              ? "bg-primary/10"
              : "bg-gradient-to-br from-primary to-primary-strong"
          )}>
            <Building className={cn("h-3 w-3", mounted && theme === "dark" ? "text-primary" : "text-white")} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-[var(--text-primary)] truncate">
              {organization.name}
            </div>
            <div className="text-[10px] text-[var(--text-secondary)]">{displayType}</div>
          </div>
          <button
            onClick={onShowOrgSettings}
            className="flex items-center text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors border border-[var(--border-color)] rounded px-1.5 py-0.5 hover:bg-[var(--bg-tertiary)]"
          >
            <Settings className="mr-0.5 h-2.5 w-2.5" />
            Manage
          </button>
        </div>

        <DropdownMenuSeparator className="bg-[var(--border-color)]" />

        {/* Create Team */}
        <DropdownMenuItem
          onClick={onShowCreateTeam}
          className="flex items-center space-x-2 p-2 cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
        >
          <div className="h-6 w-6 rounded bg-[var(--bg-tertiary)] flex items-center justify-center">
            <Users className="h-3 w-3 text-[var(--text-secondary)]" />
          </div>
          <div className="flex-1">
            <div className="text-xs font-medium text-[var(--text-primary)]">Create Team</div>
            <div className="text-[10px] text-[var(--text-secondary)]">Collaborate with others</div>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
