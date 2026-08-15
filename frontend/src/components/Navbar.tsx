import React from 'react';
import { Database, ShieldCheck, LogOut, BarChart2, MessageSquare } from 'lucide-react';
import type { User, LinkedDatabase } from '../types';

interface NavbarProps {
  user: User | null;
  activeDb: LinkedDatabase | null;
  mode: 'query' | 'analysis';
  onModeChange: (mode: 'query' | 'analysis') => void;
  onLogout: () => void;
  onSelectDbClick: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  activeDb,
  mode,
  onModeChange,
  onLogout,
  onSelectDbClick,
}) => {
  return (
    <nav className="h-16 border-b border-slate-800 bg-[#0B0F17]/80 backdrop-blur-md sticky top-0 z-50 px-6 flex items-center justify-between">
      <div className="flex items-center space-x-3 cursor-pointer" onClick={onSelectDbClick}>
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Database className="w-5 h-5 text-white" />
        </div>
        <div>
          <span className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
            Basewise
          </span>
          <span className="text-[10px] tracking-wider uppercase font-semibold text-cyan-400 block -mt-1">
            Database Intelligence
          </span>
        </div>
      </div>

      {activeDb && (
        <div className="flex items-center space-x-4">
          <button
            onClick={onSelectDbClick}
            className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-800 border border-slate-700 text-sm text-slate-200 transition-colors"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="font-medium">{activeDb.display_name}</span>
            <span className="text-xs text-slate-400">({activeDb.db_type})</span>
          </button>

          <div className="flex bg-slate-900/90 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => onModeChange('query')}
              className={`flex items-center space-x-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'query'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-md shadow-cyan-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Query Mode</span>
            </button>
            <button
              onClick={() => onModeChange('analysis')}
              className={`flex items-center space-x-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'analysis'
                  ? 'bg-gradient-to-r from-purple-500 to-indigo-600 text-white shadow-md shadow-purple-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" />
              <span>Analysis Mode</span>
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center space-x-4">
        {user && (
          <div className="flex items-center space-x-3">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-medium text-slate-300">{user.email}</div>
              <div className="text-[10px] text-cyan-400 flex items-center justify-end space-x-1">
                <ShieldCheck className="w-3 h-3" />
                <span>Encrypted Session</span>
              </div>
            </div>
            <button
              onClick={onLogout}
              title="Logout"
              className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};
