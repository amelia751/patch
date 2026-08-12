"use client";

import { useTransition } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { requestProviderCheck } from "@/lib/api/actions";

/**
 * Triggers the same code path Cloud Scheduler drives (roadmap §10.5).
 *
 * Failures are surfaced verbatim rather than swallowed: the whole point of the
 * button is to show whether the enqueue actually happened.
 */
export function CheckNowButton({ providerId = "google" }: { providerId?: string }) {
  const [pending, startTransition] = useTransition();

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          const outcome = await requestProviderCheck(providerId, "dashboard");
          if (outcome.ok) {
            toast.success(outcome.message);
          } else {
            toast.error("Provider check not enqueued", { description: outcome.message });
          }
        })
      }
    >
      <RefreshCw className={pending ? "size-4 animate-spin" : "size-4"} />
      Check {providerId} now
    </Button>
  );
}
