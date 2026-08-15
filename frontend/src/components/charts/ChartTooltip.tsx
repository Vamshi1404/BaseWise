import React from 'react';
import type { TooltipContentProps } from 'recharts';
import { formatValue } from './chartTheme';

type ChartTooltipProps = TooltipContentProps;

/**
 * Custom dark-themed tooltip that replaces Recharts' default white box.
 * Rendered as a glass panel (see .chart-tooltip styles in index.css).
 */
export const ChartTooltip: React.FC<ChartTooltipProps> = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="chart-tooltip">
      {label !== undefined && label !== null && String(label) !== '' && (
        <div className="chart-tooltip-label">{String(label)}</div>
      )}
      <div className="chart-tooltip-rows">
        {payload.map((entry, i) => {
          const color = typeof entry.color === 'string' ? entry.color : undefined;
          const name = String(entry.name ?? entry.dataKey ?? '');
          return (
            <div key={`${String(entry.dataKey ?? entry.name ?? '')}-${i}`} className="chart-tooltip-row">
              <span className="chart-tooltip-dot" style={{ background: color ?? '#06B6D4' }} />
              <span className="chart-tooltip-name">{name}</span>
              <span className="chart-tooltip-value">{formatValue(entry.value)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
