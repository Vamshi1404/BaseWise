import axios from 'axios';
import type {
  AuthTokens, User, LinkedDatabase, SchemaData,
  Conversation, Message, QueryResultPayload, AnalysisResultPayload
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT access token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh token on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post<AuthTokens>(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem('access_token', res.data.access_token);
          localStorage.setItem('refresh_token', res.data.refresh_token);
          originalRequest.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(originalRequest);
        } catch {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// --- Auth APIs ---
export const authApi = {
  signup: (data: { email: string; password: string }) =>
    api.post<AuthTokens>('/auth/signup', data),
  login: (data: { email: string; password: string }) =>
    api.post<AuthTokens>('/auth/login', data),
  me: () => api.get<User>('/auth/me'),
};

// --- Database APIs ---
export const dbApi = {
  list: () => api.get<LinkedDatabase[]>('/databases'),
  link: (data: { display_name: string; connection_url: string; db_type?: string }) =>
    api.post<LinkedDatabase>('/databases', data),
  get: (id: string) => api.get<LinkedDatabase>(`/databases/${id}`),
  unlink: (id: string) => api.delete(`/databases/${id}`),
  test: (id: string) => api.post<{ status: string; message: string }>(`/databases/${id}/test`),
  getSchema: (id: string) => api.get<SchemaData>(`/databases/${id}/schema`),
  refreshSchema: (id: string) => api.post<SchemaData>(`/databases/${id}/schema/refresh`),
};

// --- Conversation & Messaging APIs ---
export const convApi = {
  list: (dbId: string, mode: 'query' | 'analysis' = 'query') =>
    api.get<Conversation[]>(`/databases/${dbId}/conversations?mode=${mode}`),
  create: (dbId: string, mode: 'query' | 'analysis' = 'query') =>
    api.post<Conversation>(`/databases/${dbId}/conversations`, { mode }),
  getMessages: (convId: string) =>
    api.get<Message[]>(`/conversations/${convId}/messages`),

  // SSE Streaming message sender (tokens + statuses + final result)
  sendMessageStream: (
    convId: string,
    content: string,
    onStatus: (statusMsg: string) => void,
    onToken: (delta: string) => void,
    onResult: (result: QueryResultPayload) => void,
    onError: (err: string) => void
  ) => {
    const token = localStorage.getItem('access_token');
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/conversations/${convId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ content }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`);
        }
        const reader = response.body?.getReader();
        if (!reader) return;
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const block of lines) {
            if (!block.trim()) continue;
            const eventMatch = block.match(/^event: (.*)$/m);
            const dataMatch = block.match(/^data: (.*)$/m);

            const event = eventMatch ? eventMatch[1].trim() : 'message';
            const dataStr = dataMatch ? dataMatch[1].trim() : '';

            if (!dataStr) continue;

            if (event === 'done') {
              continue; // stream complete marker
            }

            try {
              const data = JSON.parse(dataStr);
              if (event === 'status') {
                onStatus(data.message);
              } else if (event === 'token') {
                onToken(data.delta ?? '');
              } else if (event === 'result') {
                onResult(data);
              } else if (event === 'error') {
                onError(data.message);
              }
            } catch (e) {
              console.error('SSE parse error', e);
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          onError(err.message || 'Stream connection failed');
        }
      });

    return () => controller.abort();
  },
};

// --- Analysis APIs ---
export const analysisApi = {
  suggest: (dbId: string) =>
    api.post<{ suggestions: string[] }>(`/databases/${dbId}/analysis/suggest`),
  execute: (convId: string, prompt: string) =>
    api.post<{
      status: string;
      chart_data?: any;
      python_code?: string;
      execution_ms?: number;
      error?: string;
    }>(`/conversations/${convId}/analysis/execute`, { prompt }),

  // SSE Streaming analysis executor
  executeStream: (
    convId: string,
    prompt: string,
    onStatus: (statusMsg: string) => void,
    onResult: (result: AnalysisResultPayload) => void,
    onError: (err: string) => void
  ) => {
    const token = localStorage.getItem('access_token');
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/conversations/${convId}/analysis/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ prompt }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`);
        }
        const reader = response.body?.getReader();
        if (!reader) return;
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const block of lines) {
            if (!block.trim()) continue;
            const eventMatch = block.match(/^event: (.*)$/m);
            const dataMatch = block.match(/^data: (.*)$/m);

            const event = eventMatch ? eventMatch[1].trim() : 'message';
            const dataStr = dataMatch ? dataMatch[1].trim() : '';

            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              if (event === 'status') {
                onStatus(data.message);
              } else if (event === 'result') {
                onResult(data);
              } else if (event === 'error') {
                onError(data.message);
              }
            } catch (e) {
              console.error('SSE parse error', e);
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          onError(err.message || 'Stream connection failed');
        }
      });

    return () => controller.abort();
  },
};
