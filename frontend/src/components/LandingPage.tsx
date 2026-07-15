import React from 'react';
import { ArrowRight, Brain, ShieldCheck, Database } from 'lucide-react';

const GithubIcon = ({ size = 24 }: { size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    stroke="currentColor"
    strokeWidth="2"
    fill="none"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);

interface LandingPageProps {
  onGetStarted: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onGetStarted }) => {
  return (
    <div className="app-container animate-fade-in">
      {/* Hero Section */}
      <section className="landing-hero">
        <h1 className="landing-title">
          Analyze GitHub Portfolios with <span className="glow-text-purple">AI</span> & <span className="glow-text-cyan">Redis RAG</span>
        </h1>
        <p className="landing-subtitle">
          RedisRAG fetches public repositories, processes README documentation, generates semantic embeddings in Redis Vector Database, and provides a grounded, AI-powered chat interface using Google Gemini.
        </p>
        <button onClick={onGetStarted} className="btn-glowing">
          Get Started <ArrowRight size={20} />
        </button>
      </section>

      {/* Feature Grid */}
      <section className="features-grid">
        <div className="feature-card glass-panel">
          <div className="feature-icon">
            <GithubIcon size={24} />
          </div>
          <h3 className="feature-title">GitHub Extraction</h3>
          <p className="feature-desc">
            Instantly download developer details, public repositories, and README documents concurrently via GitHub's API.
          </p>
        </div>

        <div className="feature-card glass-panel">
          <div className="feature-icon">
            <Database size={24} />
          </div>
          <h3 className="feature-title">Redis Vector Store</h3>
          <p className="feature-desc">
            Generate and index 3072-dimensional embeddings directly in Redis Stack using in-memory cosine similarity metrics.
          </p>
        </div>

        <div className="feature-card glass-panel">
          <div className="feature-icon">
            <Brain size={24} />
          </div>
          <h3 className="feature-title">Grounded AI Chat</h3>
          <p className="feature-desc">
            Ask complex architectural questions. RAG pipeline grounds answers with repository sources, avoiding hallucinations.
          </p>
        </div>

        <div className="feature-card glass-panel">
          <div className="feature-icon">
            <ShieldCheck size={24} />
          </div>
          <h3 className="feature-title">Secure OTP Auth</h3>
          <p className="feature-desc">
            Protect endpoints with passwordless Email OTP verification stored with active TTL expiration inside Redis cache.
          </p>
        </div>
      </section>

      {/* Architecture flow section */}
      <section style={{ padding: '4rem 2rem', textAlign: 'center', maxWidth: '900px', margin: '0 auto' }}>
        <h2 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: '1.5rem' }}>How RAG Works under the Hood</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '2rem', marginTop: '3rem' }}>
          <div className="glass-card" style={{ padding: '2rem' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--primary)', marginBottom: '1rem' }}>01</div>
            <h4 style={{ fontWeight: 700, marginBottom: '0.5rem', color: 'white' }}>Retrieve</h4>
            <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5 }}>
              Query converted to embedding. Redis pulls the most similar README chunks in microseconds.
            </p>
          </div>
          <div className="glass-card" style={{ padding: '2rem' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--secondary)', marginBottom: '1rem' }}>02</div>
            <h4 style={{ fontWeight: 700, marginBottom: '0.5rem', color: 'white' }}>Augment</h4>
            <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5 }}>
              Insert retrieved README content directly into the model's system prompt instructions.
            </p>
          </div>
          <div className="glass-card" style={{ padding: '2rem' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, color: 'white', marginBottom: '1rem' }}>03</div>
            <h4 style={{ fontWeight: 700, marginBottom: '0.5rem', color: 'white' }}>Generate</h4>
            <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5 }}>
              Google Gemini processes the prompt to generate grounded, fact-checked portfolios insights.
            </p>
          </div>
        </div>
      </section>
      
      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--border-color)', padding: '2rem', textAlign: 'center', fontSize: '0.875rem', color: 'rgba(255,255,255,0.3)', marginTop: '4rem' }}>
        &copy; {new Date().getFullYear()} RedisRAG. Built with FastAPI, React, TypeScript & Redis.
      </footer>
    </div>
  );
};
