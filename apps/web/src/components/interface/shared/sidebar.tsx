"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
import {
  LayoutDashboard,
  Settings,
  Waypoints,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface NavItem {
  title: string;
  href: string;
  icon: React.ReactNode;
  disabled?: boolean;
  external?: boolean;
}

export function SidebarNavItems({
  items,
  pathname,
}: {
  items: NavItem[];
  pathname: string;
}) {
  return items?.length ? (
    <div className="space-y-1">
      {items.map((item, index) => {
        const isActive = pathname === item.href;

        const itemContent = (
          <div
            className={cn(
              "flex items-center justify-center p-3 rounded-md transition-all duration-200 group",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-[var(--text-secondary)] hover:text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)]"
            )}
          >
            <div className="h-5 w-5 flex-shrink-0 transition-transform duration-200 group-hover:scale-110">
              {item.icon}
            </div>
          </div>
        );

        return (
          <div key={index}>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  {!item.disabled && item.href ? (
                    <Link
                      href={item.href}
                      target={item.external ? "_blank" : ""}
                      rel={item.external ? "noreferrer" : ""}
                    >
                      {itemContent}
                    </Link>
                  ) : (
                    <span className="cursor-not-allowed opacity-60">
                      {itemContent}
                    </span>
                  )}
                </TooltipTrigger>
                <TooltipContent
                  side="right"
                  className="bg-primary text-primary-foreground border-primary"
                >
                  <p>{item.title}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        );
      })}
    </div>
  ) : null;
}

interface SidebarProps {
  organizationName?: string | null;
  onWidthChange?: (width: number) => void;
}

const Sidebar = ({ onWidthChange }: SidebarProps) => {
  const pathname = usePathname();
  const [sidebarWidth] = useState(64); // compact width

  const navItems: NavItem[] = [
    { title: "Workspace", href: "/", icon: <LayoutDashboard className="h-5 w-5" /> },
    { title: "Settings", href: "/settings", icon: <Settings className="h-5 w-5" /> },
  ];

  useEffect(() => {
    onWidthChange?.(sidebarWidth);
  }, [sidebarWidth, onWidthChange]);

  return (
    <div
      className="flex-shrink-0 flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-color)] transition-colors"
      style={{ width: `${sidebarWidth}px` }}
    >
      <div className="px-2 py-3 border-b border-[var(--border-color)]">
        <Link href="/hub">
          <div className="flex items-center justify-center p-3 rounded-md bg-primary text-primary-foreground cursor-pointer transition-all duration-200 hover:bg-primary-hover hover:scale-105 active:scale-95">
            <Waypoints className="h-6 w-6" />
          </div>
        </Link>
      </div>

      <nav className="flex-1 px-2 py-3">
        <SidebarNavItems items={navItems} pathname={pathname || ""} />
      </nav>
    </div>
  );
};

export default Sidebar;

