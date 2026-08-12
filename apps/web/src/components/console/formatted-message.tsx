"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/chat/code-block/code-block";
import { DiffBlock } from "@/components/chat/code-block/diff-block";
import { TerminalBlock } from "@/components/chat/code-block/terminal-block";

interface FormattedMessageProps {
  content: string;
  className?: string;
}

/**
 * FormattedMessage - Renders markdown content with proper styling for the console.
 * 
 * Supports:
 * - Headers (h1, h2, h3)
 * - Lists (ordered and unordered)
 * - Code blocks with syntax highlighting
 * - Inline code
 * - Tables
 * - Bold, italic, strikethrough
 * - Links
 * - Blockquotes
 */
export function FormattedMessage({ content, className = "" }: FormattedMessageProps) {
  if (!content) return null;
  return (
    <div className={`text-[13px] leading-relaxed prose prose-sm max-w-none ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headers
          h1: ({ ...props }) => (
            <h1 className="text-[16px] font-bold mt-4 mb-2 text-[var(--text-tertiary)] border-b border-[var(--border-color)] pb-2" {...props} />
          ),
          h2: ({ ...props }) => (
            <h2 className="text-[14px] font-semibold mt-3 mb-1.5 text-[var(--text-tertiary)]" {...props} />
          ),
          h3: ({ ...props }) => (
            <h3 className="text-[13px] font-semibold mt-2 mb-1 text-[var(--text-tertiary)]" {...props} />
          ),
          
          // Paragraphs
          p: ({ ...props }) => (
            <div className="my-2 text-[var(--text-tertiary)]" {...props} />
          ),
          
          // Lists
          ul: ({ ...props }) => (
            <ul className="list-disc pl-5 my-2 space-y-1 text-[var(--text-tertiary)]" {...props} />
          ),
          ol: ({ ...props }) => (
            <ol className="list-decimal pl-5 my-2 space-y-1 text-[var(--text-tertiary)]" {...props} />
          ),
          li: ({ ...props }) => (
            <li className="text-[var(--text-tertiary)]" {...props} />
          ),
          
          // Links
          a: ({ ...props }) => (
            <a className="text-primary hover:underline" target="_blank" rel="noopener noreferrer" {...props} />
          ),
          
          // Emphasis
          strong: ({ ...props }) => (
            <strong className="font-semibold text-[var(--text-primary)]" {...props} />
          ),
          em: ({ ...props }) => (
            <em className="italic" {...props} />
          ),
          
          // Blockquotes — inset panel (Cursor-style callout), not a colored rail
          blockquote: ({ ...props }) => (
            <blockquote
              className="my-2.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3.5 py-3 text-[var(--text-tertiary)] leading-relaxed [&_div]:!my-1.5 [&_div:first-child]:!mt-0 [&_div:last-child]:!mb-0"
              {...props}
            />
          ),
          
          // Horizontal rule
          hr: ({ ...props }) => (
            <hr className="my-4 border-[var(--border-color)]" {...props} />
          ),
          
          // Inline code
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || "");
            const language = match ? match[1] : "";
            const code = String(children).replace(/\n$/, "");
            
            // Check if it's a code block (has language) or inline code
            const isCodeBlock = match || code.includes("\n");
            
            if (isCodeBlock) {
              // Terminal blocks — render with TerminalBlock (command + output + expand/collapse)
              const isTerminal = language === 'terminal' || language === 'bash' || language === 'sh';
              if (isTerminal) {
                return <TerminalBlock code={code} onCopy={() => navigator.clipboard.writeText(code)} />;
              }

              // Diff blocks — render with DiffBlock (file icons, colored lines)
              const isDiff = language === 'diff' || code.startsWith('---') || code.startsWith('+++');
              if (isDiff) {
                return <DiffBlock code={code} onCopy={() => navigator.clipboard.writeText(code)} />;
              }

              return (
                <CodeBlock 
                  code={code} 
                  language={language || "text"} 
                  onCopy={() => navigator.clipboard.writeText(code)} 
                />
              );
            }
            
            // Inline code
            return (
              <code 
                className="px-1.5 py-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded text-[12px] font-mono"
                {...props}
              >
                {children}
              </code>
            );
          },
          
          // Pre (for code blocks without language)
          pre: ({ children, ...props }) => {
            // ReactMarkdown wraps code blocks in pre > code
            // We handle this in the code component above
            return <>{children}</>;
          },
          
          // Tables
          table: ({ ...props }) => (
            <div className="my-3 overflow-x-auto">
              <table className="min-w-full border border-[var(--border-color)] rounded-lg overflow-hidden" {...props} />
            </div>
          ),
          thead: ({ ...props }) => (
            <thead className="bg-[var(--bg-secondary)]" {...props} />
          ),
          tbody: ({ ...props }) => (
            <tbody className="divide-y divide-[var(--border-color)]" {...props} />
          ),
          tr: ({ ...props }) => (
            <tr className="border-b border-[var(--border-color)] last:border-b-0" {...props} />
          ),
          th: ({ ...props }) => (
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-[var(--text-primary)] border-r border-[var(--border-color)] last:border-r-0" {...props} />
          ),
          td: ({ ...props }) => (
            <td className="px-3 py-2 text-[12px] text-[var(--text-secondary)] border-r border-[var(--border-color)] last:border-r-0" {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default FormattedMessage;
