"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function DeploymentPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/monitor");
  }, [router]);

  return (
    <div className="flex-1 flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#10b981] mx-auto mb-4"></div>
        <p className="text-sm text-[var(--text-secondary)]">Redirecting to Monitor...</p>
      </div>
    </div>
  );
}
