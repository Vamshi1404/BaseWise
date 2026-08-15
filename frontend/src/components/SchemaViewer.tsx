import React, { useState } from 'react';
import { Table, Key, Link, Hash, RefreshCw, Search, ChevronDown, ChevronRight, Layers } from 'lucide-react';
import type { SchemaData, TableSchema } from '../types';

interface SchemaViewerProps {
  schema: SchemaData | null;
  loading: boolean;
  onRefresh: () => void;
}

export const SchemaViewer: React.FC<SchemaViewerProps> = ({ schema, loading, onRefresh }) => {
  const [search, setSearch] = useState('');
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});

  const toggleTable = (tableName: string) => {
    setExpandedTables((prev) => ({ ...prev, [tableName]: !prev[tableName] }));
  };

  const filteredTables = schema?.tables.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase())
  ) || [];

  return (
    <div className="h-full flex flex-col bg-[#0B0F17]/90 border-r border-slate-800/80 w-72 shrink-0 select-none">
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            Schema Explorer
          </h2>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors disabled:opacity-50"
          title="Refresh schema"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="p-3 border-b border-slate-800/60">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Filter tables..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="p-4 text-center text-xs text-slate-500 animate-pulse">
            Loading schema...
          </div>
        ) : filteredTables.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">
            No tables found
          </div>
        ) : (
          filteredTables.map((t) => (
            <TableItem
              key={t.name}
              table={t}
              isExpanded={!!expandedTables[t.name]}
              onToggle={() => toggleTable(t.name)}
            />
          ))
        )}
      </div>

      {schema && (
        <div className="p-3 border-t border-slate-800/80 text-[10px] text-slate-500 flex justify-between">
          <span>{schema.tables.length} tables</span>
          <span className="uppercase font-mono">{schema.dialect}</span>
        </div>
      )}
    </div>
  );
};

const TableItem: React.FC<{
  table: TableSchema;
  isExpanded: boolean;
  onToggle: () => void;
}> = ({ table, isExpanded, onToggle }) => {
  return (
    <div className="rounded-lg overflow-hidden transition-colors">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800/50 hover:text-white rounded-lg transition-colors group"
      >
        <div className="flex items-center space-x-2 truncate">
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0 group-hover:text-slate-300" />
          )}
          <Table className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
          <span className="truncate font-medium">{table.name}</span>
        </div>
        {table.row_count !== undefined && table.row_count !== null && (
          <span className="text-[10px] text-slate-500 font-mono">
            ~{table.row_count}
          </span>
        )}
      </button>

      {isExpanded && (
        <div className="pl-7 pr-2 py-1 space-y-1 text-[11px] font-mono border-l border-slate-800 ml-4 my-1">
          {table.columns.map((c) => (
            <div key={c.name} className="flex items-center justify-between text-slate-400 py-0.5">
              <div className="flex items-center space-x-1.5 truncate">
                {c.primary_key ? (
                  <Key className="w-3 h-3 text-amber-400 shrink-0" />
                ) : (
                  <Hash className="w-3 h-3 text-slate-600 shrink-0" />
                )}
                <span className={c.primary_key ? 'text-amber-300 font-semibold' : ''}>
                  {c.name}
                </span>
              </div>
              <span className="text-[10px] text-slate-600 truncate ml-2">{c.type}</span>
            </div>
          ))}

          {table.foreign_keys?.map((fk, idx) => (
            <div key={idx} className="flex items-center space-x-1 text-[10px] text-purple-400 py-0.5">
              <Link className="w-3 h-3 shrink-0" />
              <span className="truncate">
                {fk.column} → {fk.references_table}.{fk.references_column}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
