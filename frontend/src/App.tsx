import { useState, useEffect } from 'react';
import { LandingPage } from './components/LandingPage';
import { AuthCard } from './components/AuthCard';
import { DashboardWorkspace } from './components/DashboardWorkspace';
import { api } from './services/api';
import './App.css';

function App() {
  const [view, setView] = useState<'landing' | 'auth' | 'dashboard'>('landing');
  const [userEmail, setUserEmail] = useState('');
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Check login on startup
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem('token');
      if (storedToken) {
        try {
          const userData = await api.getMe();
          if (userData && userData.email) {
            setUserEmail(userData.email);
            setView('dashboard');
          } else {
            api.logout();
          }
        } catch (err) {
          console.error("Session expired or invalid:", err);
          api.logout();
        }
      }
      setCheckingAuth(false);
    };
    initAuth();
  }, []);

  const handleAuthSuccess = (_token: string, email: string) => {
    setUserEmail(email);
    setView('dashboard');
  };

  const handleLogout = () => {
    api.logout();
    setUserEmail('');
    setView('landing');
  };

  if (checkingAuth) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', backgroundColor: '#030014', color: 'white', fontFamily: 'sans-serif' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="animate-spin" style={{ width: '40px', height: '40px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: '#a855f7', borderRadius: '50%', margin: '0 auto 1rem auto' }}></div>
          <p style={{ opacity: 0.6, fontSize: '0.9rem' }}>Initializing secure session...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {view === 'landing' && (
        <LandingPage onGetStarted={() => setView('auth')} />
      )}
      {view === 'auth' && (
        <AuthCard onBack={() => setView('landing')} onSuccess={handleAuthSuccess} />
      )}
      {view === 'dashboard' && (
        <DashboardWorkspace userEmail={userEmail} onLogout={handleLogout} />
      )}
    </>
  );
}

export default App;
