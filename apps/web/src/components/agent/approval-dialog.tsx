'use client';

/**
 * ApprovalDialog - Request user approval for agent actions.
 */

import React, { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { AlertCircle, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ApprovalDialogProps {
  message: string;
  options: string[];
  context?: Record<string, unknown>;
  timeoutSeconds?: number;
  onResponse: (option: string) => void;
  className?: string;
}

export function ApprovalDialog({
  message,
  options,
  context,
  timeoutSeconds,
  onResponse,
  className,
}: ApprovalDialogProps) {
  const [timeLeft, setTimeLeft] = useState(timeoutSeconds);

  // Countdown timer
  useEffect(() => {
    if (!timeoutSeconds) return;

    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev === undefined || prev <= 1) {
          clearInterval(timer);
          // Auto-reject on timeout
          onResponse(options[options.length - 1] || 'Reject');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [timeoutSeconds, options, onResponse]);

  return (
    <div className={cn(
      'rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4',
      className
    )}>
      {/* Header */}
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-sm font-medium text-yellow-200">
            Approval Required
          </h4>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {message}
          </p>
        </div>
        
        {/* Countdown */}
        {timeLeft !== undefined && timeLeft > 0 && (
          <div className="flex items-center gap-1 text-xs text-yellow-400">
            <Clock className="w-3 h-3" />
            <span>{timeLeft}s</span>
          </div>
        )}
      </div>

      {/* Context */}
      {context && Object.keys(context).length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-secondary)]">
            View details
          </summary>
          <pre className="mt-2 p-2 text-xs font-mono bg-[#1a1a1a] rounded overflow-x-auto">
            {JSON.stringify(context, null, 2)}
          </pre>
        </details>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 mt-4">
        {options.map((option, index) => {
          // First option is usually "Approve", last is usually "Reject"
          const isApprove = index === 0;
          
          return (
            <Button
              key={option}
              onClick={() => onResponse(option)}
              variant={isApprove ? 'default' : 'outline'}
              size="sm"
              className={cn(
                isApprove 
                  ? 'bg-green-600 hover:bg-green-700' 
                  : 'border-red-500/50 text-red-400 hover:bg-red-500/10'
              )}
            >
              {option}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
