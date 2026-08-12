"use client";

import { useState, KeyboardEvent } from "react";
import { ClarificationInfo } from "@/lib/architecture-context";

interface ClarificationCardProps {
  clarification: ClarificationInfo;
  onResponse: (response: string) => void;
}

export function ClarificationCard({ clarification, onResponse }: ClarificationCardProps) {
  const [customInput, setCustomInput] = useState("");

  const handleCustomSubmit = () => {
    if (customInput.trim()) {
      onResponse(customInput);
      setCustomInput("");
    }
  };

  const handleCustomKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleCustomSubmit();
    }
  };

  return (
    <div className="text-[13px] text-[var(--text-tertiary)] leading-relaxed">
      <p className="font-medium mb-2">{clarification.question}</p>
      {clarification.context && (
        <p className="text-[var(--text-secondary)] mb-3">{clarification.context}</p>
      )}
      {clarification.options && clarification.options.length > 0 && (
        <div className="flex flex-col gap-1.5 mt-3 max-w-md">
          {clarification.options.map((option, idx) => (
            <button
              key={idx}
              onClick={() => onResponse(option)}
              className="px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-secondary)] text-left text-[var(--text-primary)] transition-colors border border-[var(--border-color)] text-[12px]"
            >
              {option}
            </button>
          ))}
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={handleCustomKeyPress}
            placeholder="Other - Type what you want us to do differently"
            className="w-full px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-secondary)] text-left text-[var(--text-primary)] transition-colors border border-[var(--border-color)] text-[12px] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--border-color)]"
          />
        </div>
      )}
    </div>
  );
}
