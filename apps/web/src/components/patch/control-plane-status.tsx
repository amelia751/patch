import { readReadiness } from "@/lib/api/client";
import { StatusPill } from "@/components/patch/status";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Live readiness of the control plane, per dependency.
 *
 * Shown in the header on every page because a partly wired control plane is
 * the normal state during the build: the read model can be connected while the
 * event transport is not. A single green dot would hide that.
 */
export async function ControlPlaneStatus() {
  const result = await readReadiness();

  if (result.status !== "ok") {
    return <StatusPill tone="fail" label="Control plane unreachable" />;
  }

  const checks = result.data.checks;
  const down = checks.filter((check) => !check.ready);

  const pill =
    down.length === 0 ? (
      <StatusPill tone="pass" label={`Control plane ready · ${result.data.environment}`} />
    ) : (
      <StatusPill
        tone="human"
        label={`${down.length} of ${checks.length} dependencies unwired`}
      />
    );

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-default">{pill}</span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-sm">
          <div className="space-y-1">
            {checks.map((check) => (
              <div key={check.name} className="flex items-baseline gap-2 text-xs">
                <span className={check.ready ? "text-state-pass" : "text-state-human"}>
                  {check.ready ? "ready" : "not ready"}
                </span>
                <span className="font-mono">{check.name}</span>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
