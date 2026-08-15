import React, { useId } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import type { ChartSpec } from '../../types';
import {
  CHART_FONT,
  AXIS_TICK_COLOR,
  AXIS_LINE_COLOR,
  GRID_COLOR,
  GRADIENTS,
  formatCompact,
  formatValue,
} from './chartTheme';

interface ScatterTooltipProps {
  active?: boolean;
  payload?: any[];
  xKey: string;
  yKey: string;
  zKey?: string;
}

/* Dark-themed tooltip showing the point's x, y and (optional) z values. */
const ScatterTooltip: React.FC<ScatterTooltipProps> = ({
  active,
  payload,
  xKey,
  yKey,
  zKey,
}) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0]?.payload ?? {};
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">
        {xKey} × {yKey}
      </div>
      <div className="chart-tooltip-rows">
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: GRADIENTS[0].top }} />
          <span className="chart-tooltip-name">{xKey}</span>
          <span className="chart-tooltip-value">{formatValue(d[xKey])}</span>
        </div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: GRADIENTS[0].base }} />
          <span className="chart-tooltip-name">{yKey}</span>
          <span className="chart-tooltip-value">{formatValue(d[yKey])}</span>
        </div>
        {zKey && d[zKey] !== undefined && (
          <div className="chart-tooltip-row">
            <span className="chart-tooltip-dot" style={{ background: '#8B5CF6' }} />
            <span className="chart-tooltip-name">{zKey}</span>
            <span className="chart-tooltip-value">{formatValue(d[zKey])}</span>
          </div>
        )}
      </div>
    </div>
  );
};

interface ScatterVizProps {
  spec: ChartSpec;
}

/**
 * Scatter chart — correlation between two numeric fields. Points are
 * individual result rows; an optional third numeric drives bubble size (z).
 * Rendered inside ChartRenderer's themed card + ResponsiveContainer.
 */
export const ScatterViz: React.FC<ScatterVizProps> = ({ spec }) => {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const { data = [], x_key, y_keys = [], z_key } = spec;
  const keys = Object.keys(data[0] || {});
  const xKey = x_key || keys[0] || 'x';
  const yKey = y_keys[0] || keys[1] || 'y';
  const zKey = z_key;

  const axisTick = { fill: AXIS_TICK_COLOR, fontSize: 11, fontFamily: CHART_FONT };

  return (
    <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
      <defs>
        <linearGradient id={`${uid}-scatter`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={GRADIENTS[0].top} />
          <stop offset="100%" stopColor={GRADIENTS[0].base} />
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={GRID_COLOR} />
      <XAxis
        type="number"
        dataKey={xKey}
        name={xKey}
        tick={axisTick}
        tickLine={false}
        axisLine={{ stroke: AXIS_LINE_COLOR }}
        tickFormatter={formatCompact}
        tickMargin={8}
      />
      <YAxis
        type="number"
        dataKey={yKey}
        name={yKey}
        tick={axisTick}
        tickLine={false}
        axisLine={false}
        width={48}
        tickFormatter={formatCompact}
      />
      {zKey ? <ZAxis type="number" dataKey={zKey} range={[30, 140]} /> : null}
      <Tooltip
        content={<ScatterTooltip xKey={xKey} yKey={yKey} zKey={zKey} />}
        cursor={{ stroke: AXIS_LINE_COLOR, strokeDasharray: '3 3' }}
      />
      <Scatter
        data={data}
        dataKey={yKey}
        fill={`url(#${uid}-scatter)`}
        fillOpacity={0.9}
        stroke="#0B0F17"
        strokeWidth={1}
        isAnimationActive
        animationDuration={750}
        animationEasing="ease-out"
      />
    </ScatterChart>
  );
};
