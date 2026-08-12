"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
import { useAuth } from "@/lib/auth-context";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  User,
  Bell,
  Shield,
  CreditCard,
  Palette,
  Key,
  Sparkles,
  Zap,
} from "lucide-react";

interface UserSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UserSettingsDialog({ open, onOpenChange }: UserSettingsDialogProps) {
  const [activeTab, setActiveTab] = useState("profile");
  const { theme, setTheme } = useTheme();
  const { user } = useAuth();

  const displayName = user?.display_name || "User";
  const displayEmail = user?.email || "";

  const tabs = [
    { id: "profile", label: "Profile", icon: User },
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "security", label: "Security", icon: Shield },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "appearance", label: "Appearance", icon: Palette },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] p-0">
        <div className="flex h-[500px]">
          {/* Sidebar */}
          <div className="w-48 border-r border-[var(--border-color)] p-4 bg-[var(--bg-secondary)]/30">
            <DialogHeader className="mb-4">
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
                Settings
              </DialogTitle>
            </DialogHeader>
            <nav className="space-y-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 text-xs rounded-lg transition-all duration-200",
                    activeTab === tab.id
                      ? "bg-primary text-white shadow-sm"
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
            {activeTab === "profile" && (
              <ProfileTab displayName={displayName} displayEmail={displayEmail} />
            )}
            {activeTab === "notifications" && <NotificationsTab />}
            {activeTab === "security" && <SecurityTab />}
            {activeTab === "billing" && <BillingTab />}
            {activeTab === "appearance" && <AppearanceTab theme={theme} setTheme={setTheme} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ProfileTab({ displayName, displayEmail }: { displayName: string; displayEmail: string }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Profile Information</h3>
        <div className="flex items-start gap-4 mb-6">
          <div className="h-16 w-16 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center shadow-lg">
            <User className="h-8 w-8 text-white" />
          </div>
          <div className="flex-1">
            <Button
              variant="outline"
              size="sm"
              className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            >
              Upload Photo
            </Button>
            <p className="text-[10px] text-[var(--text-secondary)] mt-1.5">JPG, PNG or GIF. Max 2MB.</p>
          </div>
        </div>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Display Name</Label>
            <Input
              defaultValue={displayName}
              className="h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
            />
          </div>
          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Email</Label>
            <Input
              defaultValue={displayEmail}
              className="h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
            />
          </div>
        </div>
      </div>
      <div className="flex justify-end pt-4 border-t border-[var(--border-color)]">
        <Button size="sm" className="bg-primary hover:bg-primary-hover text-white text-xs shadow-sm">
          Save Changes
        </Button>
      </div>
    </div>
  );
}

function NotificationsTab() {
  const notifications = [
    { label: "Email notifications", desc: "Receive updates via email", enabled: true },
    { label: "Push notifications", desc: "Browser push notifications", enabled: true },
    { label: "Project updates", desc: "When project status changes", enabled: false },
    { label: "Team invites", desc: "When invited to a team", enabled: true },
  ];

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Notification Preferences</h3>
      <div className="space-y-1">
        {notifications.map((item, i) => (
          <div
            key={i}
            className="flex items-center justify-between py-3 px-3 rounded-lg hover:bg-[var(--bg-secondary)]/50 transition-colors"
          >
            <div>
              <p className="text-xs font-medium text-[var(--text-primary)]">{item.label}</p>
              <p className="text-[10px] text-[var(--text-secondary)]">{item.desc}</p>
            </div>
            <button
              className={cn(
                "h-5 w-9 rounded-full relative transition-colors duration-200",
                item.enabled ? "bg-primary" : "bg-[var(--bg-tertiary)]"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200",
                  item.enabled ? "right-0.5" : "left-0.5"
                )}
              />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SecurityTab() {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Security Settings</h3>
      <div className="space-y-3">
        <div className="p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-[var(--bg-tertiary)] flex items-center justify-center">
                <Key className="h-4 w-4 text-[var(--text-secondary)]" />
              </div>
              <div>
                <p className="text-xs font-medium text-[var(--text-primary)]">Password</p>
                <p className="text-[10px] text-[var(--text-secondary)]">Last changed 30 days ago</p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            >
              Change
            </Button>
          </div>
        </div>
        <div className="p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-[var(--bg-tertiary)] flex items-center justify-center">
                <Shield className="h-4 w-4 text-[var(--text-secondary)]" />
              </div>
              <div>
                <p className="text-xs font-medium text-[var(--text-primary)]">Two-factor authentication</p>
                <p className="text-[10px] text-[var(--text-secondary)]">Add an extra layer of security</p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            >
              Enable
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function BillingTab() {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Billing & Plan</h3>
      <div className="p-5 rounded-xl border-2 border-primary bg-gradient-to-br from-[#2d9d9b]/5 to-[#2d9d9b]/10">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-primary">Free Plan</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/20 text-primary font-medium">
            Current
          </span>
        </div>
        <p className="text-xs text-[var(--text-secondary)] mb-4">3 projects, 1 team member, basic features</p>
        <Button size="sm" className="w-full bg-primary hover:bg-primary-hover text-white text-xs shadow-sm">
          <Zap className="h-3.5 w-3.5 mr-1.5" />
          Upgrade to Pro
        </Button>
      </div>
    </div>
  );
}

function AppearanceTab({
  theme,
  setTheme,
}: {
  theme: string;
  setTheme: (theme: "light" | "dark") => void;
}) {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Appearance</h3>
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={() => setTheme("light")}
          className={cn(
            "p-4 rounded-xl border-2 transition-all duration-200 text-left",
            theme === "light"
              ? "border-primary shadow-sm"
              : "border-[var(--border-color)] hover:border-[var(--text-secondary)]"
          )}
        >
          <div className="h-20 rounded-lg bg-white border border-gray-200 mb-3 overflow-hidden">
            <div className="h-4 bg-gray-100 border-b border-gray-200" />
            <div className="p-2 space-y-1">
              <div className="h-2 w-16 bg-gray-200 rounded" />
              <div className="h-2 w-12 bg-gray-200 rounded" />
            </div>
          </div>
          <p className="text-xs font-medium text-[var(--text-primary)]">Light</p>
        </button>
        <button
          onClick={() => setTheme("dark")}
          className={cn(
            "p-4 rounded-xl border-2 transition-all duration-200 text-left",
            theme === "dark"
              ? "border-primary shadow-sm"
              : "border-[var(--border-color)] hover:border-[var(--text-secondary)]"
          )}
        >
          <div className="h-20 rounded-lg bg-gray-900 border border-gray-700 mb-3 overflow-hidden">
            <div className="h-4 bg-gray-800 border-b border-gray-700" />
            <div className="p-2 space-y-1">
              <div className="h-2 w-16 bg-gray-700 rounded" />
              <div className="h-2 w-12 bg-gray-700 rounded" />
            </div>
          </div>
          <p className="text-xs font-medium text-[var(--text-primary)]">Dark</p>
        </button>
      </div>
    </div>
  );
}

