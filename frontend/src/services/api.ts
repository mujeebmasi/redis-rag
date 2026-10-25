const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

export type IndexingStatus = 'not_started' | 'processing' | 'completed' | 'failed';

export interface GitHubAnalyzeResponse {
  username: string;
  status: IndexingStatus;
  message: string;
}

export interface IndexingProgress {
  detail?: string;
  current_repo?: string;
  repos_done?: number;
  repos_total?: number;
  chunks_done?: number;
}

export interface GitHubStatusResponse {
  username: string;
  status: IndexingStatus;
  phase: string | null;
  progress: IndexingProgress | null;
  error: string | null;
  profile: GitHubProfileResponse | null;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  redis: string;
  gemini_key_set: boolean;
  groq_key_set: boolean;
  github_token_set: boolean;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
}

/**
 * fetch() wrapper: JSON in, JSON out, and readable error messages.
 * The backend puts its message in `detail`; a network failure
 * (server down or still waking up) has no response at all.
 */
async function request<T>(path: string, init: RequestInit = {}, fallbackError = 'Request failed.'): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    });
  } catch {
    throw new Error("Can't reach the server. It may still be waking up, so try again in a minute.");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const detail = typeof err?.detail === 'string' ? err.detail : null;
    throw new Error(detail || fallbackError);
  }
  return res.json();
}

export const api = {
  health(): Promise<HealthResponse> {
    return request('/health', {}, 'Server health check failed.');
  },

  analyzeProfile(username: string, refresh = false): Promise<GitHubAnalyzeResponse> {
    return request(
      '/github/analyze',
      { method: 'POST', body: JSON.stringify({ username, refresh }) },
      'Failed to start the analysis.',
    );
  },

  getStatus(username: string): Promise<GitHubStatusResponse> {
    return request(`/github/status/${encodeURIComponent(username)}`, {}, 'Failed to check status.');
  },

  askQuestion(username: string, question: string): Promise<ChatResponse> {
    return request(
      '/chat',
      { method: 'POST', body: JSON.stringify({ username, question }) },
      'Failed to query AI.',
    );
  },
};
