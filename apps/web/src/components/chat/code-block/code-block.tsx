"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { useSyntaxTheme } from "./syntax-theme";

interface CodeBlockProps {
  code: string;
  language: string;
  onCopy?: (code: string) => void;
}

// Map our language names to Prism language identifiers
const LANG_MAP: Record<string, string> = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  py: "python", rb: "ruby", yml: "yaml", sh: "bash",
  terminal: "bash", tf: "hcl", text: "text", txt: "text",
};

function normalizeLang(lang: string): string {
  return LANG_MAP[lang] || lang;
}

export function CodeBlock({ code, language, onCopy }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const { prismTheme, preStyle, codeStyle } = useSyntaxTheme();

  const handleCopy = () => {
    if (onCopy) onCopy(code);
    else navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const prismLang = normalizeLang(language);
  const displayLabel = language === "terminal" ? "Terminal" : language;

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-[var(--border-color)] max-w-full relative group not-prose">
      {/* Header */}
      <div className="bg-[var(--bg-tertiary)] px-3 py-1.5 flex items-center justify-between border-b border-[var(--border-color)]">
        <span className="text-[10px] font-mono text-[var(--text-secondary)] uppercase">
          {displayLabel}
        </span>
        <button
          onClick={handleCopy}
          className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors opacity-0 group-hover:opacity-100"
        >
          {copied ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
        </button>
      </div>

      {/* Code with syntax highlighting */}
      <SyntaxHighlighter
        language={prismLang}
        style={prismTheme}
        customStyle={preStyle}
        codeTagProps={{ style: codeStyle }}
        wrapLines
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
