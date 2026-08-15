import React, { useState, useEffect } from 'react';
import { authApi } from './api/client';
import type { User, LinkedDatabase } from './types';
import { Navbar } from './components/Navbar';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { DatabaseWorkspace } from './pages/DatabaseWorkspace';
import { AddDatabaseModal } from './components/AddDatabaseModal';

export const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [authView, setAuthView] = useState<'login' | 'register'>('login');
  const [activeDb, setActiveDb] = useState<LinkedDatabase | null>(null);
  const [mode, setMode] = useState<'query' | 'analysis'>('query');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const checkAuth = () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    authApi.me()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
    setActiveDb(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0B0F17] flex items-center justify-center text-cyan-400 text-xs font-mono">
        Initializing Basewise Platform...
      </div>
    );
  }

  if (!user) {
    return authView === 'login' ? (
      <LoginPage
        onLoginSuccess={checkAuth}
        onSwitchToRegister={() => setAuthView('register')}
      />
    ) : (
      <RegisterPage
        onRegisterSuccess={checkAuth}
        onSwitchToLogin={() => setAuthView('login')}
      />
    );
  }

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-100 font-sans flex flex-col">
      <Navbar
        user={user}
        activeDb={activeDb}
        mode={mode}
        onModeChange={setMode}
        onLogout={handleLogout}
        onSelectDbClick={() => setActiveDb(null)}
      />

      <main className="flex-1 overflow-hidden">
        {activeDb ? (
          <DatabaseWorkspace
            database={activeDb}
            mode={mode}
          />
        ) : (
          <DashboardPage
            onSelectDatabase={(db) => setActiveDb(db)}
            onOpenAddModal={() => setIsAddModalOpen(true)}
          />
        )}
      </main>

      <AddDatabaseModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSuccess={(newDb) => setActiveDb(newDb)}
      />
    </div>
  );
};

export default App;
