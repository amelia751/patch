/**
 * Explicit dark tokens for account UI. Dialogs render in a portal at document
 * root, so they must not rely on page-scoped or light-theme CSS variables.
 */
export const authModalContent =
  "max-w-md border border-[#2e2e2e] bg-[#1a1a1a] text-[#e0e0e0] shadow-2xl";

export const authField =
  "bg-[#141414] border-[#2e2e2e] text-[#e0e0e0] placeholder:text-[#666666]";

export const authLabel = "text-[#888888]";

export const authMuted = "text-[#888888]";

export const authHeadline = "text-[#e0e0e0]";

export const authOutlineButton =
  "border-[#2e2e2e] bg-transparent text-[#e0e0e0] hover:bg-[#252525] hover:text-[#e0e0e0]";

export const authDividerLine = "border-[#2e2e2e]";

export const authOrChipBg = "bg-[#1a1a1a]";

export const authIconButtonMuted =
  "text-[#888888] hover:text-[#e0e0e0]";
