import React from 'react';
import { Database, Clock, ChevronRight, Trash2, CheckCircle2 } from 'lucide-react';
import type { LinkedDatabase } from '../types';

interface DatabaseCardProps {
  db: LinkedDatabase;
  onSelect: (db: LinkedDatabase) => void;
  onUnlink: (dbId: string) => void;
}

export const DatabaseCard: React.FC<DatabaseCardProps> = ({ db, onSelect, onUnlink }) => {
  return (
    <div className="group relative glass-card rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-cyan-500/10 border border-slate-800 hover:border-cyan-500/40">
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 rounded-xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-cyan-400 group-hover:scale-110 group-hover:bg-cyan-500/10 transition-all">
            <Database className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-100 group-hover:text-cyan-300 transition-colors">
              {db.display_name}
            </h3>
            <div className="flex items-center space-x-2 mt-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider bg-slate-800 text-slate-400 border border-slate-700">
                {db.db_type}
              </span>
              <span className="inline-flex items-center text-[11px] text-emerald-400 space-x-1">
                <CheckCircle2 className="w-3 h-3" />
                <span>Connected</span>
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(`Unlink ${db.display_name}? Encrypted credentials will be permanently deleted.`)) {
              onUnlink(db.id);
            }
          }}
          className="p-2 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 opacity-0 group-hover:opacity-100 transition-all"
          title="Unlink database"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center space-x-1.5">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          <span>
            {db.last_schema_scan_at
              ? `Scanned ${new Date(db.last_schema_scan_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
              : 'Schema scanned'}
          </span>
        </div>

        <button
          onClick={() => onSelect(db)}
          className="flex items-center space-x-1 font-medium text-cyan-400 hover:text-cyan-300 group-hover:translate-x-1 transition-all"
        >
          <span>Open Workspace</span>
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
