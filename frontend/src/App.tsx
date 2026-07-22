import { useState } from 'react';
import { LandingPage } from './components/LandingPage';
import { DashboardWorkspace } from './components/DashboardWorkspace';
import './App.css';

function App() {
  const [view, setView] = useState<'landing' | 'dashboard'>('dashboard');

  return (
    <>
      {view === 'landing' && (
        <LandingPage onGetStarted={() => setView('dashboard')} />
      )}
      {view === 'dashboard' && (
        <DashboardWorkspace 
          userEmail="developer@redisrag.local" 
          onLogout={() => setView('landing')} 
        />
      )}
    </>
  );
}

export default App;
