import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { GitHubProfileResponse } from '../services/api';
import { ChatConsole } from './ChatConsole';
import { Search, Loader, Star, GitFork, BookOpen, AlertCircle, RefreshCw } from 'lucide-react';

interface DashboardWorkspaceProps {
  userEmail: string;
  onLogout: () => void;
}

export const DashboardWorkspace: React.FC<DashboardWorkspaceProps> = ({ userEmail, onLogout }) => {
  const [usernameInput, setUsernameInput] = useState('');
  const [activeUsername, setActiveUsername] = useState<string | null>(null);
  const [indexingStatus, setIndexingStatus] = useState<'not_started' | 'processing' | 'completed' | 'failed'>('not_started');
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<GitHubProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Poll status when "processing"
  useEffect(() => {
    if (!activeUsername || indexingStatus !== 'processing') return;

    let isSubscribed = true;
    const checkStatus = async () => {
      try {
        const response = await api.getStatus(activeUsername);
        if (!isSubscribed) return;

        if (response.status === 'completed' && response.profile) {
          setIndexingStatus('completed');
          setProfile(response.profile);
        } else if (response.status === 'failed') {
          setIndexingStatus('failed');
          setError(response.error || 'Indexing task failed unexpectedly.');
        }
      } catch (err: any) {
        if (!isSubscribed) return;
        // Don't stop polling on single request fail, it could be temporary network glitch
        console.error("Status polling failed:", err);
      }
    };

    // Poll every 2 seconds
    const intervalId = setInterval(checkStatus, 2000);
    checkStatus(); // Check immediately on mount/update

    return () => {
      isSubscribed = false;
      clearInterval(intervalId);
    };
  }, [activeUsername, indexingStatus]);

  const handleStartAnalysis = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetUsername = usernameInput.trim().toLowerCase();
    if (!targetUsername) return;

    setLoading(true);
    setError(null);
    setProfile(null);
    setIndexingStatus('not_started');
    setActiveUsername(targetUsername);

    try {
      const response = await api.analyzeProfile(targetUsername);
      setIndexingStatus(response.status as any || 'processing');
    } catch (err: any) {
      setError(err.message || 'Failed to request analysis.');
      setIndexingStatus('failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Workspace Header */}
      <header className="workspace-header">
        <div className="workspace-logo">
          <BookOpen size={24} style={{ color: 'var(--primary)' }} />
          <span>Redis<span className="glow-text-purple">RAG</span></span>
        </div>
        <div className="workspace-user">
          <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>{userEmail}</span>
          <button onClick={onLogout} className="btn-secondary">Logout</button>
        </div>
      </header>

      {/* Workspace Main Panels */}
      <main className="workspace-body animate-fade-in">
        {/* Left Column: GitHub Analyzer & Repos */}
        <section className="panel-left">
          <div className="panel-content">
            {/* Input Form */}
            <div className="ingest-card glass-panel" style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-title)', marginBottom: '0.75rem' }}>Analyze GitHub Profile</h3>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                Fetch public repositories, split README content, generate vector embeddings, and save to Redis vector store.
              </p>
              
              <form onSubmit={handleStartAnalysis} style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <Search size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted-dim)' }} />
                  <input
                    type="text"
                    className="input-field"
                    style={{ paddingLeft: '2.75rem' }}
                    placeholder="Enter GitHub Username (e.g. torvalds)"
                    value={usernameInput}
                    onChange={(e) => setUsernameInput(e.target.value)}
                    disabled={loading || indexingStatus === 'processing'}
                    required
                  />
                </div>
                <button 
                  type="submit" 
                  className="btn-glowing" 
                  style={{ padding: '0.5rem 1.5rem', borderRadius: '10px', fontSize: '0.95rem' }}
                  disabled={loading || indexingStatus === 'processing'}
                >
                  {loading ? <Loader className="animate-spin" size={16} /> : 'Analyze'}
                </button>
              </form>

              {/* Status Indicators */}
              {indexingStatus !== 'not_started' && (
                <div className="status-indicator">
                  <span className={`status-badge ${indexingStatus}`}>
                    {indexingStatus === 'processing' && <RefreshCw size={12} className="animate-spin" />}
                    {indexingStatus}
                  </span>
                  <div style={{ flex: 1, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    {indexingStatus === 'processing' && 'Scraping repositories and inserting vector chunks into Redis Stack...'}
                    {indexingStatus === 'completed' && `${profile?.repositories.length || 0} repositories scanned. RAG model initialized.`}
                    {indexingStatus === 'failed' && (error || 'Something went wrong.')}
                  </div>
                </div>
              )}
            </div>

            {/* Profile Info & Repos list */}
            {profile && indexingStatus === 'completed' && (
              <div className="animate-fade-in">
                {/* Profile Card */}
                <div className="profile-card glass-panel">
                  {profile.avatar_url ? (
                    <img src={profile.avatar_url} alt={profile.name || activeUsername || ''} className="profile-avatar" />
                  ) : (
                    <div className="profile-avatar" style={{ background: 'var(--bg-light-badge)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-title)' }}>
                      {activeUsername?.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="profile-details">
                    <h4 className="profile-name">{profile.name || activeUsername}</h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--secondary)' }}>@{profile.username}</p>
                    {profile.bio && <p className="profile-bio">{profile.bio}</p>}
                    
                    <div className="profile-stats-grid">
                      <div>
                        <div className="profile-stat-val">{profile.public_repos}</div>
                        <div className="profile-stat-lbl">Repos</div>
                      </div>
                      <div>
                        <div className="profile-stat-val">{profile.followers}</div>
                        <div className="profile-stat-lbl">Followers</div>
                      </div>
                      <div>
                        <div className="profile-stat-val">{profile.following}</div>
                        <div className="profile-stat-lbl">Following</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Repositories */}
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-title)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span>Scanned Repositories</span>
                  <span style={{ fontSize: '0.8rem', padding: '0.1rem 0.5rem', background: 'var(--bg-light-badge)', borderRadius: '10px', color: 'var(--text-muted)' }}>
                    {profile.repositories.length}
                  </span>
                </h3>

                <div className="repos-container">
                  {profile.repositories.map((repo) => (
                    <div key={repo.name} className="repo-card glass-panel glass-card">
                      <div className="repo-header">
                        <a 
                          href={repo.url} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="repo-name"
                        >
                          {repo.name}
                        </a>
                        {repo.has_readme && <span className="badge-readme">Indexed</span>}
                      </div>
                      {repo.description && <p className="repo-desc">{repo.description}</p>}
                      
                      <div className="repo-footer">
                        {repo.language && <span style={{ color: 'var(--text-title)', fontWeight: 500 }}>{repo.language}</span>}
                        <span className="repo-stat"><Star size={12} /> {repo.stars}</span>
                        <span className="repo-stat"><GitFork size={12} /> {repo.forks}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Initial empty workspace helper */}
            {indexingStatus === 'not_started' && !loading && (
              <div style={{ textAlign: 'center', padding: '4rem 2rem', color: 'var(--text-muted-dim)' }}>
                <AlertCircle size={32} style={{ margin: '0 auto 1rem auto', opacity: 0.5 }} />
                <p>Start by entering a GitHub username above to build your vector search index context.</p>
              </div>
            )}
          </div>
        </section>

        {/* Right Column: RAG Chat Console */}
        <section className="panel-right">
          <ChatConsole username={activeUsername} indexingStatus={indexingStatus} />
        </section>
      </main>
    </div>
  );
};
