import React from 'react';
import { FunnelChart, Funnel, LabelList, Tooltip, Cell } from 'recharts';
import type { ChartSpec } from '../../types';
import {
  CHART_FONT,
  AXIS_TICK_COLOR,
  GRADIENTS,
  formatValue,
} from './chartTheme';

interface FunnelTooltipProps {
  active?: boolean;
  payload?: any[];
  nameKey: string;
  valueKey: string;
  first: number;
}

/* Dark-themed tooltip: stage, count, and % retained vs the first (largest) stage. */
const FunnelTooltip: React.FC<FunnelTooltipProps> = ({
  active,
  payload,
  nameKey,
  valueKey,
  first,
}) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0]?.payload ?? {};
  const value = Number(d[valueKey]) || 0;
  const pct = first > 0 ? Math.round((value / first) * 100) : 100;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{String(d[nameKey] ?? '')}</div>
      <div className="chart-tooltip-rows">
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: GRADIENTS[0].base }} />
          <span className="chart-tooltip-name">{valueKey}</span>
          <span className="chart-tooltip-value">{formatValue(value)}</span>
        </div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#64748B' }} />
          <span className="chart-tooltip-name">retained</span>
          <span className="chart-tooltip-value">{pct}%</span>
        </div>
      </div>
    </div>
  );
};

interface FunnelVizProps {
  spec: ChartSpec;
}

/**
 * Funnel chart — conversion/drop-off across ordered lifecycle stages.
 * Data rows are sorted largest-first; each label shows its % of the top stage.
 * Rendered inside ChartRenderer's themed card + ResponsiveContainer.
 */
export const FunnelViz: React.FC<FunnelVizProps> = ({ spec }) => {
  const { data = [], x_key, y_keys = [] } = spec;
  const keys = Object.keys(data[0] || {});
  const nameKey = x_key || keys[0] || 'name';
  const valueKey = y_keys[0] || keys[1] || 'value';
  const first = Number(data[0]?.[valueKey]) || 0;

  const animDuration = data.length > 8 ? 500 : 750;

  return (
    <FunnelChart margin={{ top: 8, right: 48, left: 8, bottom: 4 }}>
      <Tooltip content={<FunnelTooltip nameKey={nameKey} valueKey={valueKey} first={first} />} />
      <Funnel
        data={data}
        dataKey={valueKey}
        nameKey={nameKey}
        isAnimationActive
        animationDuration={animDuration}
        animationEasing="ease-out"
        stroke="#0B0F17"
        strokeWidth={2}
      >
        <LabelList
          position="right"
          fill={AXIS_TICK_COLOR}
          fontSize={11}
          fontFamily={CHART_FONT}
          stroke="none"
          formatter={(value: unknown) => {
            const pct = first > 0 ? Math.round((Number(value) / first) * 100) : 100;
            return `${pct}%`;
          }}
        />
        {data.map((_, i) => (
          <Cell key={`cell-${i}`} fill={GRADIENTS[i % GRADIENTS.length].base} fillOpacity={0.9} />
        ))}
      </Funnel>
    </FunnelChart>
  );
};
