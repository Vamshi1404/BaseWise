/*
 * Chart theme — derived from the app's existing dark theme
 * (index.css tokens + Tailwind slate/cyan/blue/violet palette used across
 * Navbar, badges, cards and buttons) so charts feel native to Basewise.
 */

export interface ChartColor {
  top: string;
  base: string;
}

/** Solid palette — used for pie/donut slices and legend dots. */
export const PALETTE: string[] = [
  '#06B6D4', // cyan-500  (primary accent)
  '#3B82F6', // blue-500  (primary accent)
  '#8B5CF6', // violet-500 (analysis mode accent)
  '#10B981', // emerald-500 (success)
  '#F59E0B', // amber-500  (warning)
  '#F43F5E', // rose-500   (danger)
  '#6366F1', // indigo-500
  '#14B8A6', // teal-500
  '#0EA5E9', // sky-500
  '#EC4899', // pink-500
];

/**
 * Vertical gradients per series: brighter shade at top fading into the base
 * color at the bottom — used for bar fills and line strokes.
 */
export const GRADIENTS: ChartColor[] = [
  { top: '#22D3EE', base: '#0891B2' }, // cyan-400  -> cyan-600
  { top: '#60A5FA', base: '#2563EB' }, // blue-400  -> blue-600
  { top: '#A78BFA', base: '#7C3AED' }, // violet-400 -> violet-600
  { top: '#34D399', base: '#059669' }, // emerald-400 -> emerald-600
  { top: '#FBBF24', base: '#D97706' }, // amber-400 -> amber-600
  { top: '#FB7185', base: '#E11D48' }, // rose-400  -> rose-600
  { top: '#818CF8', base: '#4F46E5' }, // indigo-400 -> indigo-600
  { top: '#2DD4BF', base: '#0D9488' }, // teal-400  -> teal-600
  { top: '#38BDF8', base: '#0284C7' }, // sky-400   -> sky-600
  { top: '#F472B6', base: '#DB2777' }, // pink-400  -> pink-600
];

export const CHART_FONT = "'Inter', system-ui, -apple-system, sans-serif";

export const AXIS_TICK_COLOR = '#94A3B8';            // slate-400
export const AXIS_LINE_COLOR = '#1E293B';            // slate-800
export const GRID_COLOR = 'rgba(148, 163, 184, 0.10)';
export const TOOLTIP_BG = 'rgba(15, 23, 42, 0.96)'; // slate-900
export const TOOLTIP_BORDER = '#334155';            // slate-700

const compactFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

/** 1234 -> "1,234", 1.2M+, 45k style for axis ticks. */
export function formatCompact(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return String(value ?? '');
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, '')}k`;
  return compactFormatter.format(value);
}

/** Friendly value formatting for tooltips (no 1.23456 spam). */
export function formatValue(value: unknown): string {
  if (typeof value === 'number' && !Number.isNaN(value)) {
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
  }
  if (value === null || value === undefined) return '—';
  return String(value);
}
