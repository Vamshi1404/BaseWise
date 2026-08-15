import React, { useState, useEffect } from 'react';
import { Database, Plus, Sparkles, Shield, Cpu } from 'lucide-react';
import { dbApi } from '../api/client';
import type { LinkedDatabase } from '../types';
import { DatabaseCard } from '../components/DatabaseCard';

interface DashboardPageProps {
  onSelectDatabase: (db: LinkedDatabase) => void;
  onOpenAddModal: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onSelectDatabase,
  onOpenAddModal,
}) => {
  const [databases, setDatabases] = useState<LinkedDatabase[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDatabases = () => {
    setLoading(true);
    dbApi.list().then((res) => {
      setDatabases(res.data);
    }).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDatabases();
  }, []);

  const handleUnlink = async (dbId: string) => {
    try {
      await dbApi.unlink(dbId);
      setDatabases((prev) => prev.filter((d) => d.id !== dbId));
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
            Your Linked Databases
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-xl">
            Basewise uses deterministic SQLAlchemy schema extraction and sandboxed E2B execution to run plain English queries and business analysis safely.
          </p>
        </div>

        <button
          onClick={onOpenAddModal}
          className="flex items-center space-x-2 px-6 py-3 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold text-sm shadow-lg shadow-cyan-500/25 hover:shadow-cyan-500/40 hover:scale-105 transition-all"
        >
          <Plus className="w-5 h-5" />
          <span>Link New Database</span>
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-44 glass-card rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : databases.length === 0 ? (
        <div className="text-center py-16 px-6 glass-panel rounded-3xl border border-slate-800 space-y-6 max-w-2xl mx-auto">
          <div className="w-16 h-16 rounded-3xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-cyan-400 mx-auto">
            <Database className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-slate-200">No Database Linked Yet</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Link your Supabase PostgreSQL database credentials to start querying, generating explainable SQL, and running proactive business analysis.
            </p>
          </div>
          <button
            onClick={onOpenAddModal}
            className="inline-flex items-center space-x-2 px-6 py-3 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold text-sm shadow-lg shadow-cyan-500/25 hover:scale-105 transition-all"
          >
            <Plus className="w-5 h-5" />
            <span>Link Your Supabase Database</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {databases.map((db) => (
            <DatabaseCard
              key={db.id}
              db={db}
              onSelect={onSelectDatabase}
              onUnlink={handleUnlink}
            />
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
        <div className="glass-panel p-6 rounded-2xl border border-slate-800/80 space-y-2">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/10 text-cyan-400 flex items-center justify-center">
            <Shield className="w-5 h-5" />
          </div>
          <h4 className="text-sm font-bold text-slate-200">Hardcoded Schema Extractor</h4>
          <p className="text-xs text-slate-400">
            Deterministic SQLAlchemy introspection extracts schema metadata safely without LLM risk.
          </p>
        </div>

        <div className="glass-panel p-6 rounded-2xl border border-slate-800/80 space-y-2">
          <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
            <Cpu className="w-5 h-5" />
          </div>
          <h4 className="text-sm font-bold text-slate-200">Sandboxed Execution (E2B)</h4>
          <p className="text-xs text-slate-400">
            All code runs in ephemeral isolated E2B cloud microVMs with strict memory security.
          </p>
        </div>

        <div className="glass-panel p-6 rounded-2xl border border-slate-800/80 space-y-2">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <Sparkles className="w-5 h-5" />
          </div>
          <h4 className="text-sm font-bold text-slate-200">2-Pass Self-Recheck Engine</h4>
          <p className="text-xs text-slate-400">
            Pass 1 generates candidate SQL; Pass 2 critiques joins and filters before running in sandbox.
          </p>
        </div>
      </div>
    </div>
  );
};
