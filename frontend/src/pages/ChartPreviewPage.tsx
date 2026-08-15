import React, { useState } from 'react';
import { ChartRenderer } from '../components/ChartRenderer';
import type { ChartSpec } from '../types';

/* Dev-only preview harness — open with #/chart-preview in the URL.
 * Renders realistic query results for bar / line / donut charts to visually
 * verify styling and animations against the dark theme. */

const ridesPerCity: ChartSpec = {
  type: 'bar',
  title: 'Rides per City',
  x_key: 'city',
  y_keys: ['rides'],
  data: [
    { city: 'San Francisco', rides: 4820 },
    { city: 'Los Angeles', rides: 3955 },
    { city: 'New York', rides: 3410 },
    { city: 'Austin', rides: 2875 },
    { city: 'Seattle', rides: 2130 },
    { city: 'Chicago', rides: 1685 },
    { city: 'Denver', rides: 1204 },
    { city: 'Miami', rides: 984 },
  ],
  summary: 'San Francisco leads with 4,820 rides — about 21% of all rides.',
};

const signupsPerMonth: ChartSpec = {
  type: 'line',
  title: 'Signups per Month',
  x_key: 'month',
  y_keys: ['signups'],
  data: [
    { month: 'Sep', signups: 312 },
    { month: 'Oct', signups: 468 },
    { month: 'Nov', signups: 402 },
    { month: 'Dec', signups: 705 },
    { month: 'Jan', signups: 891 },
    { month: 'Feb', signups: 1042 },
    { month: 'Mar', signups: 1230 },
    { month: 'Apr', signups: 1188 },
    { month: 'May', signups: 1475 },
    { month: 'Jun', signups: 1690 },
    { month: 'Jul', signups: 1902 },
    { month: 'Aug', signups: 2144 },
  ],
  summary: 'Signups grew steadily from 312 to 2,144 per month — up 6.8x year over year.',
};

const rideStatus: ChartSpec = {
  type: 'pie',
  title: 'Ride Status Breakdown',
  x_key: 'status',
  y_keys: ['count'],
  data: [
    { status: 'completed', count: 12450 },
    { status: 'in_progress', count: 2130 },
    { status: 'scheduled', count: 3420 },
    { status: 'cancelled', count: 1580 },
    { status: 'pending', count: 640 },
  ],
  summary: 'Completed rides make up 61% of all ride activity.',
};

const largeCities: ChartSpec = {
  type: 'bar',
  title: 'Rides across 24 Cities (large set stress test)',
  x_key: 'city',
  y_keys: ['rides'],
  data: Array.from({ length: 24 }, (_, i) => ({
    city: `City Number ${i + 1}`,
    rides: Math.round(600 + ((i * 7919) % 4100)),
  })),
  summary: 'Longer labels exercise tick rotation; 24 categories check animation smoothness.',
};

const secondStatus: ChartSpec = {
  type: 'pie',
  title: 'Ride Status Breakdown',
  x_key: 'status',
  y_keys: ['count'],
  data: [
    { status: 'completed', count: 14800 },
    { status: 'in_progress', count: 3050 },
    { status: 'scheduled', count: 4110 },
    { status: 'cancelled', count: 980 },
    { status: 'pending', count: 420 },
  ],
  summary: 'Completed rides grew to 63% — cancellation rate dropped this month.',
};

/* Dev-only seam: scripts (or the user) can inject a real Analysis Mode chart
 * spec before load to render the exact data the backend produced. */
declare global {
  interface Window {
    __PREVIEW_ANALYSIS__?: ChartSpec | ChartSpec[];
  }
}

const analysisInjection: ChartSpec[] = (() => {
  const injected = typeof window !== 'undefined' ? window.__PREVIEW_ANALYSIS__ : undefined;
  if (!injected) return [];
  return Array.isArray(injected) ? injected : [injected];
})();

const Card: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="space-y-3">
    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
      {label}
    </div>
    {children}
  </div>
);

export const ChartPreviewPage: React.FC = () => {
  const [toggle, setToggle] = useState(false);

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-100 p-8">
      <div className="max-w-4xl mx-auto space-y-10">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
              Chart Renderer Preview
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Bar, line, donut, large-set stress, and a live data-morph toggle.
            </p>
          </div>
          <button
            onClick={() => setToggle((t) => !t)}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-xs font-semibold shadow-lg shadow-cyan-500/25 hover:scale-105 transition-all"
          >
            Update donut data (morph test)
          </button>
        </header>

        <Card label="Bar — rides per city (gradient fills, grow-in animation)">
          <ChartRenderer spec={ridesPerCity} />
        </Card>

        {analysisInjection.map((spec, i) => (
          <Card key={`analysis-${i}`} label={`Analysis Mode chart (injected real data)`}>
            <ChartRenderer spec={spec} />
          </Card>
        ))}

        <Card label="Line — signups per month (monotone + gradient area, draw-on animation)">
          <ChartRenderer spec={signupsPerMonth} />
        </Card>

        <Card label="Donut — ride status breakdown (centered total, sweep animation)">
          <ChartRenderer spec={toggle ? secondStatus : rideStatus} />
        </Card>

        <Card label="Stress — 24 categories, rotated labels">
          <ChartRenderer spec={largeCities} />
        </Card>
      </div>
    </div>
  );
};
