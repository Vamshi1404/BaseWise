import React from 'react';
import { Treemap, Tooltip } from 'recharts';
import type { ChartSpec } from '../../types';
import {
  CHART_FONT,
  GRADIENTS,
  formatCompact,
  formatValue,
} from './chartTheme';

interface TreemapTooltipProps {
  active?: boolean;
  payload?: any[];
}

const TreemapTooltip: React.FC<TreemapTooltipProps> = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0]?.payload ?? {};
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{String(d.name ?? '')}</div>
      <div className="chart-tooltip-rows">
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: GRADIENTS[0].base }} />
          <span className="chart-tooltip-name">value</span>
          <span className="chart-tooltip-value">{formatValue(d.value)}</span>
        </div>
      </div>
    </div>
  );
};

interface TreemapCellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  index?: number;
  name?: string;
  value?: number;
}

/* Custom cell: dark slate header for parent (depth 0) groups, themed gradient
 * leaves for children, with truncated labels that fit the cell bounds. */
const TreemapCell: React.FC<TreemapCellProps> = ({
  x,
  y,
  width,
  height,
  depth,
  index,
  name,
  value,
}) => {
  if (x == null || y == null || width == null || height == null || width <= 0 || height <= 0) {
    return null;
  }
  const isParent = depth === 0;
  const fill = isParent ? '#1E293B' : GRADIENTS[(index ?? 0) % GRADIENTS.length].base;
  const padX = 6;
  const padTop = 10;
  const labelArea = width - padX * 2;
  const maxChars = Math.max(1, Math.floor(labelArea / 6));

  const truncated = String(name ?? '');
  const label = truncated.length > maxChars ? `${truncated.slice(0, maxChars)}…` : truncated;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={4}
        fill={fill}
        fillOpacity={isParent ? 1 : 0.92}
        stroke="#0B0F17"
        strokeWidth={1.5}
      />
      {height > 22 && width > 30 && (
        <text
          x={x + padX}
          y={isParent ? y + height / 2 : y + padTop}
          fill={isParent ? '#94A3B8' : '#E2E8F0'}
          fontSize={11}
          fontWeight={isParent ? 700 : 500}
          fontFamily={CHART_FONT}
          textAnchor="start"
          dominantBaseline="central"
        >
          {label}
        </text>
      )}
      {!isParent && height > 40 && width > 56 && (
        <text
          x={x + padX}
          y={y + height - 10}
          fill="#94A3B8"
          fontSize={10}
          fontFamily={CHART_FONT}
          textAnchor="start"
        >
          {formatCompact(value)}
        </text>
      )}
    </g>
  );
};

interface TreemapVizProps {
  spec: ChartSpec;
}

/**
 * Treemap chart — hierarchical proportions (parent groups with nested children).
 * Rendered inside ChartRenderer's themed card + ResponsiveContainer.
 */
export const TreemapViz: React.FC<TreemapVizProps> = ({ spec }) => {
  const { data = [], value_key } = spec;
  const valueKey = value_key || 'value';
  return (
    <Treemap
      data={data}
      dataKey={valueKey}
      nameKey="name"
      stroke="#0B0F17"
      content={<TreemapCell />}
      isAnimationActive
      animationDuration={750}
      animationEasing="ease-out"
    >
      <Tooltip content={<TreemapTooltip />} />
    </Treemap>
  );
};
