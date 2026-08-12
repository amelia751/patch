interface ActionMessageProps {
  text: string;
  duration: string;
}

export function ActionMessage({ text, duration }: ActionMessageProps) {
  return (
    <div className="text-[11px] text-[var(--text-secondary)]">
      {text} <span className="opacity-50">for {duration}</span>
    </div>
  );
}
