import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { GitHubProfileResponse, IndexingProgress, IndexingStatus } from '../services/api';
import { ChatConsole } from './ChatConsole';
import { Search, Loader, Star, GitFork, BookOpen, AlertCircle, RefreshCw } from 'lucide-react';

interface DashboardWorkspaceProps {
  onLogout: () => void;
}

// After this many failed status checks in a row, stop polling and show an error
const MAX_POLL_FAILURES = 5;

/** Turn the backend's progress object into one readable line. */
function describeProgress(phase: string | null, progress: IndexingProgress | null): string {
  if (phase === 'embedding' && progress?.repos_total) {
    const current = progress.current_repo ? ` (${progress.current_repo})` : '';
    const summary = `Embedding READMEs: ${progress.repos_done ?? 0}/${progress.repos_total} repositories${current}`;
    if (progress.wait_seconds) {
      return `${summary}. Gemini's free rate limit was reached, so this pauses for about ${progress.wait_seconds}s...`;
    }
    return `${summary}...`;
  }
  return progress?.detail || 'Fetching repositories and storing vector chunks in Redis...';
}

export const DashboardWorkspace: React.FC<DashboardWorkspaceProps> = ({ onLogout }) => {
  const [usernameInput, setUsernameInput] = useState('');
  const [activeUsername, setActiveUsername] = useState<string | null>(null);
  const [indexingStatus, setIndexingStatus] = useState<IndexingStatus>('not_started');
  const [progressText, setProgressText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<GitHubProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [serverNotice, setServerNotice] = useState<string | null>(null);

  // Wake the backend up as soon as the page opens. Free Render instances
  // sleep after 15 minutes idle and need up to a minute to start again.
  useEffect(() => {
    let isSubscribed = true;
    const slowTimer = setTimeout(() => {
      if (isSubscribed) {
        setServerNotice('Waking up the server (free hosting sleeps when idle). This can take up to a minute...');
      }
    }, 3000);

    api.health()
      .then((health) => {
        if (!isSubscribed) return;
        const problems: string[] = [];
        if (health.redis !== 'ok') problems.push(`database ${health.redis}`);
        if (!health.gemini_key_set) problems.push('GOOGLE_API_KEY missing');
        if (!health.groq_key_set) problems.push('GROQ_API_KEY missing');
        setServerNotice(
          problems.length
            ? `Server setup problem: ${problems.join(', ')}. Analysis won't work until this is fixed.`
            : null,
        );
      })
      .catch((err: unknown) => {
        if (isSubscribed) setServerNotice(err instanceof Error ? err.message : 'Server is unreachable.');
      })
      .finally(() => clearTimeout(slowTimer));

    return () => {
      isSubscribed = false;
      clearTimeout(slowTimer);
    };
  }, []);

  // Poll status when "processing" — uses exponential backoff to avoid CPU starvation
  useEffect(() => {
    if (!activeUsername || indexingStatus !== 'processing') return;

    let isSubscribed = true;
    let pollCount = 0;
    let failures = 0;

    const checkStatus = async () => {
      try {
        const response = await api.getStatus(activeUsername);
        if (!isSubscribed) return;
        failures = 0;

        if (response.status === 'completed' && response.profile) {
          setIndexingStatus('completed');
          setProfile(response.profile);
        } else if (response.status === 'failed') {
          setIndexingStatus('failed');
          setError(response.error || 'Indexing task failed unexpectedly.');
        } else {
          setProgressText(describeProgress(response.phase, response.progress));
        }
      } catch (err: unknown) {
        if (!isSubscribed) return;
        failures++;
        console.error("Status polling failed:", err);
        if (failures >= MAX_POLL_FAILURES) {
          setIndexingStatus('failed');
          setError(err instanceof Error ? err.message : 'Lost contact with the server.');
        }
      }
    };

    // Exponential backoff: 2s, 4s, 6s, 8s... capped at 10s
    // This prevents hammering the free-tier server with too many requests
    const getInterval = () => Math.min(2000 + pollCount * 2000, 10000);

    let timeoutId: ReturnType<typeof setTimeout>;
    const scheduleNext = () => {
      if (!isSubscribed) return;
      pollCount++;
      timeoutId = setTimeout(async () => {
        await checkStatus();
        scheduleNext();
      }, getInterval());
    };

    checkStatus(); // Check immediately
    scheduleNext();

    return () => {
      isSubscribed = false;
      clearTimeout(timeoutId);
    };
  }, [activeUsername, indexingStatus]);

  const startAnalysis = async (targetUsername: string, refresh = false) => {
    setLoading(true);
    setError(null);
    setProfile(null);
    setProgressText(null);
    setIndexingStatus('not_started');
    setActiveUsername(targetUsername);

    try {
      await api.analyzeProfile(targetUsername, refresh);
      // Whether the job just started, was already running, or finished
      // earlier ("completed" from cache), polling the status loads the result.
      setIndexingStatus('processing');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to request analysis.');
      setIndexingStatus('failed');
    } finally {
      setLoading(false);
    }
  };

  const handleStartAnalysis = (e: React.FormEvent) => {
    e.preventDefault();
    const targetUsername = usernameInput.trim().toLowerCase();
    if (targetUsername) startAnalysis(targetUsername);
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
          <button onClick={onLogout} className="btn-secondary">Home</button>
        </div>
      </header>

      {/* Workspace Main Panels */}
      <main className="workspace-body animate-fade-in">
        {/* Left Column: GitHub Analyzer & Repos */}
        <section className="panel-left">
          <div className="panel-content">
            {/* Server wake-up / setup notice */}
            {serverNotice && (
              <div className="server-notice" role="status">
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{serverNotice}</span>
              </div>
            )}

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
                    {indexingStatus === 'processing' && (progressText || 'Fetching repositories and storing vector chunks in Redis...')}
                    {indexingStatus === 'completed' &&
                      `${profile?.total_readmes_indexed ?? 0} of ${profile?.repositories.length ?? 0} repositories have indexed READMEs. Ready to chat.`}
                    {indexingStatus === 'failed' && (error || 'Something went wrong.')}
                  </div>
                  {activeUsername && (indexingStatus === 'completed' || indexingStatus === 'failed') && (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ fontSize: '0.8rem', padding: '0.3rem 0.75rem' }}
                      onClick={() => startAnalysis(activeUsername, indexingStatus === 'completed')}
                      title="Fetch the profile again and re-embed any README that changed"
                    >
                      {indexingStatus === 'completed' ? 'Re-index' : 'Retry'}
                    </button>
                  )}
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
          {/* key: switching profile starts a fresh conversation */}
          <ChatConsole key={activeUsername ?? 'none'} username={activeUsername} indexingStatus={indexingStatus} />
        </section>
      </main>
    </div>
  );
};
