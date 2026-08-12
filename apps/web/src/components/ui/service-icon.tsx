"use client";

import { useEffect, useState } from "react";
import * as LucideIcons from "lucide-react";
import { getServiceIcon, type ServiceIcon } from "@/lib/service-icons";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";

interface ServiceIconProps {
  /** Service name (e.g., "stripe", "slack", "sendgrid") */
  name: string;
  /** Icon size in pixels */
  size?: number;
  /** Additional CSS classes */
  className?: string;
  /** Show background circle/square */
  withBackground?: boolean;
  /** Background shape */
  backgroundShape?: "circle" | "rounded" | "square";
  /** Override the icon color */
  color?: string;
}

/**
 * Universal service icon component
 * 
 * Automatically resolves icons from:
 * 1. svgl.app (full color logos)
 * 2. Simple Icons CDN (3100+ brand icons)
 * 3. Lucide (category fallbacks)
 * 
 * @example
 * <ServiceIcon name="stripe" size={24} />
 * <ServiceIcon name="slack" withBackground backgroundShape="rounded" />
 * <ServiceIcon name="unknown-service" /> // Falls back to Lucide Box icon
 */
export function ServiceIcon({
  name,
  size = 24,
  className,
  withBackground = false,
  backgroundShape = "rounded",
  color: colorOverride,
}: ServiceIconProps) {
  const [imgError, setImgError] = useState(false);
  const { theme } = useTheme();
  const iconData = getServiceIcon(name, theme as 'light' | 'dark');

  useEffect(() => {
    setImgError(false);
  }, [name, theme, iconData.type, iconData.src]);

  const color = colorOverride || iconData.color;
  const bgColor = iconData.bgColor;
  
  // Background wrapper styles
  const bgShapeClass = {
    circle: "rounded-full",
    rounded: "rounded-lg",
    square: "rounded-none",
  }[backgroundShape];
  
  const wrapperStyle = withBackground ? {
    backgroundColor: bgColor,
    padding: size * 0.25,
  } : {};
  
  const iconSize = withBackground ? size * 0.6 : size;
  
  // Render Lucide icon
  if (iconData.type === "lucide" || imgError) {
    const LucideIcon = (LucideIcons as Record<string, any>)[iconData.type === "lucide" ? iconData.src : "Box"];
    
    if (!LucideIcon) {
      const FallbackIcon = LucideIcons.Box;
      return (
        <div
          className={cn("flex items-center justify-center", withBackground && bgShapeClass, className)}
          style={wrapperStyle}
        >
          <FallbackIcon size={iconSize} style={{ color }} />
        </div>
      );
    }
    
    return (
      <div
        className={cn("flex items-center justify-center", withBackground && bgShapeClass, className)}
        style={wrapperStyle}
      >
        <LucideIcon size={iconSize} style={{ color }} />
      </div>
    );
  }
  
  // Render image icon (svgl or simple-icons CDN)
  return (
    <div
      className={cn("flex items-center justify-center", withBackground && bgShapeClass, className)}
      style={wrapperStyle}
    >
      <img
        src={iconData.src}
        alt={iconData.title}
        width={iconSize}
        height={iconSize}
        className="object-contain"
        onError={() => setImgError(true)}
        loading="lazy"
      />
    </div>
  );
}

/**
 * Service icon with badge/label
 */
export function ServiceIconBadge({
  name,
  size = 16,
  showLabel = true,
  className,
}: {
  name: string;
  size?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const { theme } = useTheme();
  const iconData = getServiceIcon(name, theme as 'light' | 'dark');
  
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1 rounded-md border",
        className
      )}
      style={{
        borderColor: iconData.color,
        backgroundColor: iconData.bgColor,
      }}
    >
      <ServiceIcon name={name} size={size} />
      {showLabel && (
        <span
          className="text-xs font-medium"
          style={{ color: iconData.color }}
        >
          {iconData.title}
        </span>
      )}
    </div>
  );
}

/**
 * Get icon data without rendering (for custom implementations)
 */
export { getServiceIcon };
export type { ServiceIcon as ServiceIconData } from "@/lib/service-icons";

