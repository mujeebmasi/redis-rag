import React, { useState } from 'react';
import { api } from '../services/api';
import { ArrowLeft, Loader, KeyRound, Mail } from 'lucide-react';

interface AuthCardProps {
  onBack: () => void;
  onSuccess: (token: string, email: string) => void;
}

export const AuthCard: React.FC<AuthCardProps> = ({ onBack, onSuccess }) => {
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [step, setStep] = useState<1 | 2>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await api.sendOtp(email.trim());
      setMessage(response.message || 'OTP sent successfully!');
      setStep(2);
    } catch (err: any) {
      setError(err.message || 'Failed to send OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.verifyOtp(email.trim(), otp.trim());
      if (response.verified && response.access_token) {
        onSuccess(response.access_token, email.trim());
      } else {
        setError(response.message || 'Invalid verification response.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to verify OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card glass-panel animate-fade-in">
        <button 
          onClick={step === 2 ? () => { setStep(1); setError(null); setMessage(null); } : onBack} 
          className="btn-secondary" 
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', marginBottom: '2rem', float: 'left' }}
        >
          <ArrowLeft size={16} /> Back
        </button>
        <div style={{ clear: 'both' }}></div>

        {step === 1 ? (
          <form onSubmit={handleSendOtp}>
            <div style={{ marginBottom: '2rem' }}>
              <div className="feature-icon" style={{ margin: '0 auto 1rem auto', background: 'rgba(168, 85, 247, 0.1)', borderColor: 'rgba(168, 85, 247, 0.2)', color: 'var(--primary)' }}>
                <Mail size={24} />
              </div>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'white', marginBottom: '0.5rem' }}>Welcome Back</h2>
              <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.5)' }}>Enter your email to receive a passwordless OTP verification code.</p>
            </div>

            <div className="input-group">
              <label className="input-label">Email Address</label>
              <input
                type="email"
                className="input-field"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
              />
            </div>

            {error && <div style={{ color: 'var(--error)', fontSize: '0.9rem', marginBottom: '1rem', textAlign: 'left' }}>{error}</div>}

            <button type="submit" className="btn-glowing" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
              {loading ? <Loader className="animate-spin" size={20} /> : 'Send Verification Code'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp}>
            <div style={{ marginBottom: '2rem' }}>
              <div className="feature-icon" style={{ margin: '0 auto 1rem auto' }}>
                <KeyRound size={24} />
              </div>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'white', marginBottom: '0.5rem' }}>Enter OTP</h2>
              <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.5)' }}>We've sent a 6-digit code to <strong style={{ color: 'white' }}>{email}</strong>.</p>
            </div>

            {message && <div style={{ color: 'var(--success)', fontSize: '0.9rem', marginBottom: '1rem', textAlign: 'left' }}>{message}</div>}

            <div className="input-group">
              <label className="input-label">6-Digit Verification Code</label>
              <input
                type="text"
                maxLength={6}
                className="input-field"
                placeholder="000000"
                style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.35em' }}
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
                disabled={loading}
              />
            </div>

            {error && <div style={{ color: 'var(--error)', fontSize: '0.9rem', marginBottom: '1rem', textAlign: 'left' }}>{error}</div>}

            <button type="submit" className="btn-glowing" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
              {loading ? <Loader className="animate-spin" size={20} /> : 'Verify & Continue'}
            </button>
            
            <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)', marginTop: '1.5rem' }}>
              Didn't receive the code?{' '}
              <button 
                type="button" 
                onClick={handleSendOtp} 
                style={{ background: 'none', border: 'none', color: 'var(--secondary)', cursor: 'pointer', fontWeight: 600, padding: 0 }}
                disabled={loading}
              >
                Resend code
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
};
