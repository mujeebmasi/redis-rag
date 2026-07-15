const BASE_URL = 'http://localhost:8000';

function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  const token = localStorage.getItem('token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export interface AuthSendOtpResponse {
  message: string;
}

export interface AuthVerifyOtpResponse {
  verified: boolean;
  message: string;
  access_token: string;
}

export interface RepositoryInfo {
  name: string;
  description: string | null;
  language: string | null;
  stars: number;
  forks: number;
  url: string;
  has_readme: boolean;
}

export interface GitHubProfileResponse {
  username: string;
  name: string | null;
  bio: string | null;
  avatar_url: string | null;
  public_repos: number;
  followers: number;
  following: number;
  repositories: RepositoryInfo[];
  total_readmes_indexed: number;
  message: string;
}

export interface GitHubAnalyzeResponse {
  username: string;
  status: string;
  message: string;
}

export interface GitHubStatusResponse {
  username: string;
  status: 'not_started' | 'processing' | 'completed' | 'failed';
  error: string | null;
  profile: GitHubProfileResponse | null;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
}

export const api = {
  async sendOtp(email: string): Promise<AuthSendOtpResponse> {
    const res = await fetch(`${BASE_URL}/auth/send-otp`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to send OTP.' }));
      throw new Error(err.detail || 'Failed to send OTP.');
    }
    return res.json();
  },

  async verifyOtp(email: string, otp: string): Promise<AuthVerifyOtpResponse> {
    const res = await fetch(`${BASE_URL}/auth/verify-otp`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email, otp }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to verify OTP.' }));
      throw new Error(err.detail || 'Failed to verify OTP.');
    }
    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem('token', data.access_token);
    }
    return data;
  },

  async getMe(): Promise<any> {
    const res = await fetch(`${BASE_URL}/auth/me`, {
      method: 'GET',
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error('Failed to retrieve user information.');
    }
    return res.json();
  },

  async analyzeProfile(username: string): Promise<GitHubAnalyzeResponse> {
    const res = await fetch(`${BASE_URL}/github/analyze`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ username }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to initiate analysis.' }));
      throw new Error(err.detail || 'Failed to initiate analysis.');
    }
    return res.json();
  },

  async getStatus(username: string): Promise<GitHubStatusResponse> {
    const res = await fetch(`${BASE_URL}/github/status/${username}`, {
      method: 'GET',
      headers: getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to check status.' }));
      throw new Error(err.detail || 'Failed to check status.');
    }
    return res.json();
  },

  async askQuestion(username: string, question: string): Promise<ChatResponse> {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ username, question }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to query AI.' }));
      throw new Error(err.detail || 'Failed to query AI.');
    }
    return res.json();
  },

  logout() {
    localStorage.removeItem('token');
  }
};
