"use client";

import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Google (lh3.googleusercontent.com) 403s the photo when the browser sends a
 * Referer from localhost or Cloud Run. `no-referrer` is required; onError
 * falls back so a blocked URL never shows the broken-image glyph.
 */
export function UserAvatar({
  src,
  name,
  className,
  fallback = null,
}: {
  src: string | null | undefined;
  name: string;
  className?: string;
  fallback?: ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?";

  if (src && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={cn("w-full h-full object-cover", className)}
      />
    );
  }

  if (fallback !== null) {
    return fallback;
  }

  return (
    <div className="w-full h-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
      <span className="font-medium text-white text-[10px]">{initials}</span>
    </div>
  );
}
