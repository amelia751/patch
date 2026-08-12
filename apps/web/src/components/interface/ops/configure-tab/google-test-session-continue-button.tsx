"use client";

import { ServiceIcon } from "@/components/ui/service-icon";
import { cn } from "@/lib/utils";
import { useTestGoogleSessionOptional } from "@/lib/test-google-session-context";

/**
 * Captures a Google session for the **customer’s app** (sandbox / Configure → Auth).
 *
 * Distinct from PatchAPI account OAuth (`sign-in-dialog.tsx`, `sign-up-dialog.tsx`): those use `GoogleIcon`
 * and no `data-patchapi-purpose` attribute.
 */
const TEST_APP_SESSION_BUTTON_CLASS =
  "w-full h-10 text-sm shadow-sm transition-colors duration-150 " +
  "border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 hover:text-gray-900 active:bg-gray-100 " +
  "dark:border-[var(--border-color)] dark:bg-[var(--bg-secondary)] dark:text-[var(--text-primary)] " +
  "dark:shadow-none dark:hover:bg-[var(--bg-tertiary)] dark:hover:text-[var(--text-primary)] dark:active:bg-[var(--bg-primary)]";

/** Same surface as “Continue with Google” in thread callouts — use for other full-width inline actions. */
export const THREAD_CALLOUT_ACTION_BUTTON_CLASS = TEST_APP_SESSION_BUTTON_CLASS;

export type GoogleTestSessionContinueButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Google mark size in px; modal and chat both use 18 by default. */
  iconSize?: number;
};

export function GoogleTestSessionContinueButton({
  className,
  children = "Continue with Google",
  iconSize = 18,
  type = "button",
  title = "Captures a Google login for testing your app in the sandbox. This is not PatchAPI account sign-in.",
  "aria-label": ariaLabel,
  ...props
}: GoogleTestSessionContinueButtonProps) {
  const testSession = useTestGoogleSessionOptional();
  const googleIconKey = testSession?.googleSessionIconGeneration ?? 0;

  const label =
    ariaLabel ??
    "Continue with Google — capture a test session for your app (not PatchAPI login)";

  return (
    <button
      type={type}
      title={title}
      aria-label={label}
      data-patchapi-purpose="google-test-app-session"
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium",
        TEST_APP_SESSION_BUTTON_CLASS,
        className
      )}
      {...props}
    >
      <ServiceIcon
        key={googleIconKey}
        name="google"
        size={iconSize}
        className="mr-2 shrink-0"
        aria-hidden
      />
      {children}
    </button>
  );
}
