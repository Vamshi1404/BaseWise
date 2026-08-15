import React, { useId } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  BarChart,
  Bar,
  Line,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Label,
} from 'recharts';
import type { ChartSpec } from '../types';
import {
  PALETTE,
  GRADIENTS,
  CHART_FONT,
  AXIS_TICK_COLOR,
  AXIS_LINE_COLOR,
  GRID_COLOR,
  formatCompact,
  formatValue,
} from './charts/chartTheme';
import { ChartTooltip } from './charts/ChartTooltip';
import { ScatterViz } from './charts/ScatterChart';
import { FunnelViz } from './charts/FunnelChart';
import { TreemapViz } from './charts/TreemapChart';

interface ChartRendererProps {
  spec?: ChartSpec | null;
}

/* Recharts defs: one vertical gradient per series for bars, a horizontal
 * stroke gradient for lines, and a soft vertical fade for area fills. */
const ChartDefs: React.FC<{ prefix: string; count: number }> = ({ prefix, count }) => (
  <defs>
    {Array.from({ length: count }, (_, i) => {
      const g = GRADIENTS[i % GRADIENTS.length];
      return (
        <React.Fragment key={i}>
          <linearGradient id={`${prefix}-bar-${i}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={g.top} />
            <stop offset="100%" stopColor={g.base} />
          </linearGradient>
          <linearGradient id={`${prefix}-line-${i}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={g.top} />
            <stop offset="100%" stopColor={g.base} />
          </linearGradient>
          <linearGradient id={`${prefix}-area-${i}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={g.base} stopOpacity={0.28} />
            <stop offset="100%" stopColor={g.base} stopOpacity={0.02} />
          </linearGradient>
        </React.Fragment>
      );
    })}
  </defs>
);

interface LegendEntry {
  value?: React.ReactNode;
  color?: string;
  dataKey?: string | number;
  type?: string;
}

/* Custom legend — small colored dots + app font, matching the dark UI. */
const ChartLegend: React.FC<{ payload?: LegendEntry[] }> = ({ payload }) => {
  const visible = (payload ?? []).filter((entry) => entry.type !== 'none');
  if (visible.length === 0) return null;
  return (
    <ul className="chart-legend">
      {visible.map((entry, i) => {
        const color =
          entry.color && !String(entry.color).startsWith('url(')
            ? entry.color
            : PALETTE[i % PALETTE.length];
        return (
          <li key={`${String(entry.value ?? entry.dataKey ?? '')}-${i}`}>
            <span className="chart-legend-dot" style={{ background: color }} />
            <span>{entry.value}</span>
          </li>
        );
      })}
    </ul>
  );
};

interface DonutCenterProps {
  viewBox?: { cx?: number; cy?: number };
  total: number;
  caption: string;
}

/* Centered total inside the donut hole. */
const DonutCenter: React.FC<DonutCenterProps> = ({ viewBox, total, caption }) => {
  const cx = viewBox?.cx ?? 0;
  const cy = viewBox?.cy ?? 0;
  return (
    <g pointerEvents="none">
      <text x={cx} y={cy - 2} textAnchor="middle" className="donut-total-text">
        {formatValue(total)}
      </text>
      <text x={cx} y={cy + 15} textAnchor="middle" className="donut-caption-text">
        {caption}
      </text>
    </g>
  );
};

/* Percentage labels around the donut (only for small slices counts). */
const renderPieLabel = (props: {
  cx?: number;
  cy?: number;
  midAngle?: number;
  innerRadius?: number;
  outerRadius?: number;
  percent?: number;
  index?: number;
}): React.ReactElement => {
  const cx = props.cx ?? 0;
  const cy = props.cy ?? 0;
  const midAngle = props.midAngle ?? 0;
  const innerRadius = props.innerRadius ?? 0;
  const outerRadius = props.outerRadius ?? 0;
  const percent = props.percent ?? 0;
  const radius = (innerRadius + outerRadius) / 2;
  const rad = (-midAngle * Math.PI) / 180;
  const x = cx + radius * Math.cos(rad);
  const y = cy + radius * Math.sin(rad);
  return (
    <text
      x={x}
      y={y}
      className="pie-label-text"
      textAnchor={x > cx ? 'start' : 'end'}
      dominantBaseline="central"
    >
      {`${Math.round(percent * 100)}%`}
    </text>
  );
};

export const ChartRenderer: React.FC<ChartRendererProps> = ({ spec }) => {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');

  if (!spec) return null;

  const { type = 'bar', title, data = [], x_key, y_keys = [] } = spec;

  if (!data || data.length === 0) return null;

  const keys = Object.keys(data[0] || {});
  const xAxisKey = x_key || keys[0] || 'label';
  const valueKeys = y_keys.length > 0 ? y_keys : keys.slice(1);
  const valueKey = valueKeys[0] || keys[1];

  const longLabels = data.some((d) => String(d[xAxisKey] ?? '').length > 12);
  const largeSet = data.length > 16;
  const animDuration = largeSet ? 500 : 750;
  const heightClass = largeSet || valueKeys.length > 1 ? 'h-80' : 'h-72';

  const axisTick = { fill: AXIS_TICK_COLOR, fontSize: 11, fontFamily: CHART_FONT };
  const xAxisProps = {
    dataKey: xAxisKey,
    tick: axisTick,
    tickLine: false as const,
    axisLine: { stroke: AXIS_LINE_COLOR },
    tickMargin: 10,
    interval: 0 as const,
    angle: longLabels ? -30 : 0,
    textAnchor: (longLabels ? 'end' : 'middle') as 'end' | 'middle',
    height: longLabels ? 64 : 36,
  };
  const yAxisProps = {
    tick: axisTick,
    tickLine: false as const,
    axisLine: false as const,
    width: 48,
    tickFormatter: formatCompact,
  };

  const cartesianMargin = { top: 8, right: 12, left: 0, bottom: longLabels ? 22 : 4 };

  const renderCartesianGrid = (
    <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={GRID_COLOR} />
  );

  const renderLegend = <Legend content={<ChartLegend />} />;

  return (
    <div className="rounded-2xl glass-card p-6 border border-slate-800 space-y-4 animate-fade-in">
      {title && (
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-slate-100">{title}</h4>
          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-400">
            {type === 'pie' ? 'donut' : `${type} chart`}
          </span>
        </div>
      )}

      {spec.summary && (
        <p className="text-xs text-slate-300 bg-slate-900/60 p-3 rounded-xl border border-slate-800">
          {spec.summary}
        </p>
      )}

      <div className={`w-full pt-2 ${heightClass}`} style={{ fontFamily: CHART_FONT }}>
        <ResponsiveContainer width="100%" height="100%">
          {type === 'scatter' ? (
            <ScatterViz spec={spec} />
          ) : type === 'funnel' ? (
            <FunnelViz spec={spec} />
          ) : type === 'treemap' ? (
            <TreemapViz spec={spec} />
          ) : type === 'line' || type === 'area' ? (
            <ComposedChart data={data} margin={cartesianMargin}>
              <ChartDefs prefix={uid} count={valueKeys.length} />
              {renderCartesianGrid}
              <XAxis {...xAxisProps} />
              <YAxis {...yAxisProps} />
              <Tooltip
                content={(props) => <ChartTooltip {...props} />}
                cursor={{ stroke: AXIS_LINE_COLOR, strokeDasharray: '3 3' }}
              />
              {renderLegend}
              {valueKeys.map((key, i) => (
                <Area
                  key={`area-${key}`}
                  dataKey={key}
                  name={String(key)}
                  type="monotone"
                  stroke="none"
                  fill={`url(#${uid}-area-${i})`}
                  legendType="none"
                  isAnimationActive
                  animationDuration={animDuration}
                  animationEasing="ease-in-out"
                />
              ))}
              {valueKeys.map((key, i) => (
                <Line
                  key={`line-${key}`}
                  dataKey={key}
                  name={String(key)}
                  type="monotone"
                  stroke={`url(#${uid}-line-${i})`}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  dot={
                    largeSet
                      ? false
                      : { r: 3.5, strokeWidth: 0, fill: GRADIENTS[i % GRADIENTS.length].top }
                  }
                  activeDot={{ r: 5, strokeWidth: 0 }}
                  isAnimationActive
                  animationDuration={animDuration}
                  animationEasing="ease-in-out"
                  animationBegin={120}
                />
              ))}
            </ComposedChart>
          ) : type === 'pie' ? (
            <PieChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <Tooltip content={(props) => <ChartTooltip {...props} />} />
              {renderLegend}
              <Pie
                data={data}
                dataKey={valueKey}
                nameKey={xAxisKey}
                cx="50%"
                cy="46%"
                innerRadius="56%"
                outerRadius="88%"
                paddingAngle={2.5}
                cornerRadius={6}
                stroke="#0B0F17"
                strokeWidth={2}
                labelLine={false}
                label={data.length <= 10 ? renderPieLabel : false}
                isAnimationActive
                animationDuration={animDuration}
                animationEasing="ease-out"
              >
                <Label
                  content={
                    <DonutCenter
                      total={data.reduce((sum, d) => sum + (Number(d[valueKey]) || 0), 0)}
                      caption={String(valueKey)}
                    />
                  }
                  position="center"
                />
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : (
            <BarChart
              data={data}
              margin={cartesianMargin}
              barCategoryGap="26%"
              barGap={5}
            >
              <ChartDefs prefix={uid} count={valueKeys.length} />
              {renderCartesianGrid}
              <XAxis {...xAxisProps} />
              <YAxis {...yAxisProps} />
              <Tooltip content={(props) => <ChartTooltip {...props} />} cursor={{ fill: 'rgba(148, 163, 184, 0.07)' }} />
              {renderLegend}
              {valueKeys.map((key, i) => (
                <Bar
                  key={key}
                  dataKey={key}
                  name={String(key)}
                  fill={`url(#${uid}-bar-${i})`}
                  radius={[5, 5, 0, 0]}
                  maxBarSize={44}
                  isAnimationActive
                  animationDuration={animDuration}
                  animationEasing="ease-out"
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
