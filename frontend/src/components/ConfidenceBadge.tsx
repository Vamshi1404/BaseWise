import React from 'react';
import { ShieldCheck, AlertTriangle, AlertCircle } from 'lucide-react';

interface ConfidenceBadgeProps {
  score?: number | null;
  label?: 'high' | 'medium' | 'low' | null;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ score, label }) => {
  if (score === undefined || score === null) return null;

  const pct = Math.round(score * 100);

  if (score >= 0.75 || label === 'high') {
    return (
      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
        <ShieldCheck className="w-3.5 h-3.5" />
        <span>Self-Rechecked {pct}% (High Confidence)</span>
      </span>
    );
  }

  if (score >= 0.5 || label === 'medium') {
    return (
      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
        <AlertTriangle className="w-3.5 h-3.5" />
        <span>Recheck Confidence {pct}% (Medium)</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
      <AlertCircle className="w-3.5 h-3.5" />
      <span>Low Confidence ({pct}%)</span>
    </span>
  );
};
