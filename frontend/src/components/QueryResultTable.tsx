import React, { useState } from 'react';
import { ArrowUpDown, Search, Download } from 'lucide-react';

interface QueryResultTableProps {
  rows?: Record<string, any>[] | null;
  rowCount?: number;
  rowsAffected?: number;
  operationType?: 'read' | 'write' | 'ddl';
  executionMs?: number;
}

export const QueryResultTable: React.FC<QueryResultTableProps> = ({
  rows,
  rowCount = 0,
  rowsAffected = 0,
  operationType = 'read',
  executionMs = 0,
}) => {
  const [filter, setFilter] = useState('');
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  if (operationType !== 'read') {
    return (
      <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-slate-300 flex items-center justify-between animate-fade-in">
        <div>
          <span className="font-semibold text-emerald-400 uppercase tracking-wider mr-2 font-mono">
            {operationType} OK
          </span>
          <span>{rowsAffected} row(s) affected</span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">{executionMs}ms</span>
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 italic animate-fade-in">
        Query executed cleanly but returned 0 rows.
      </div>
    );
  }

  const columns = Object.keys(rows[0]);

  // Filtering
  const filtered = rows.filter((r) =>
    columns.some((col) =>
      String(r[col] ?? '').toLowerCase().includes(filter.toLowerCase())
    )
  );

  // Sorting
  const sorted = [...filtered].sort((a, b) => {
    if (!sortCol) return 0;
    const valA = a[sortCol];
    const valB = b[sortCol];

    if (valA === valB) return 0;
    if (valA === null || valA === undefined) return 1;
    if (valB === null || valB === undefined) return -1;

    if (typeof valA === 'number' && typeof valB === 'number') {
      return sortAsc ? valA - valB : valB - valA;
    }
    return sortAsc
      ? String(valA).localeCompare(String(valB))
      : String(valB).localeCompare(String(valA));
  });

  const handleSort = (col: string) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  };

  const exportCsv = () => {
    const header = columns.join(',');
    const body = rows
      .map((r) => columns.map((c) => JSON.stringify(r[c] ?? '')).join(','))
      .join('\n');
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `query_result_${Date.now()}.csv`;
    a.click();
  };

  return (
    <div className="rounded-2xl bg-slate-900/90 border border-slate-800 overflow-hidden animate-fade-in">
      {/* Table controls */}
      <div className="p-3 border-b border-slate-800 flex items-center justify-between gap-3 text-xs">
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Filter results..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>

        <div className="flex items-center space-x-3 text-[11px] text-slate-400">
          <span>
            Showing <strong className="text-slate-200">{sorted.length}</strong> of {rowCount} rows
          </span>
          <span className="font-mono text-slate-500">{executionMs}ms</span>
          <button
            onClick={exportCsv}
            className="flex items-center space-x-1 px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            title="Export CSV"
          >
            <Download className="w-3 h-3" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Table body */}
      <div className="max-h-72 overflow-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 sticky top-0 uppercase text-[10px] tracking-wider">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className="px-4 py-2.5 font-semibold cursor-pointer hover:text-cyan-400 select-none transition-colors"
                >
                  <div className="flex items-center space-x-1">
                    <span>{col}</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50 text-slate-300">
            {sorted.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-2 whitespace-nowrap">
                    {row[col] === null ? (
                      <span className="text-slate-600 italic">null</span>
                    ) : typeof row[col] === 'boolean' ? (
                      <span className={row[col] ? 'text-emerald-400' : 'text-rose-400'}>
                        {String(row[col])}
                      </span>
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
