"use client";

import { Suspense } from "react";
import { AuthActionPanel } from "@/components/interface/auth/auth-action-panel";

export default function AuthActionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[#111111] text-[#888888]">
          Loading…
        </div>
      }
    >
      <AuthActionPanel />
    </Suspense>
  );
}
