import { storage } from '@/src/utils/storage';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const TOKEN_KEY = 'teebox_jwt_v1';

export type User = {
  id: string;
  email: string;
  display_name: string;
  home_course?: string;
  handicap?: number | null;
  bio?: string;
  avatar?: string | null;
};

export async function saveToken(token: string) {
  await storage.secureSet(TOKEN_KEY, token);
}

export async function getToken(): Promise<string | null> {
  const v = await storage.secureGet<string>(TOKEN_KEY, '');
  return v && typeof v === 'string' && v.length > 0 ? v : null;
}

export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

async function request<T>(path: string, opts: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}/api${path}`, { ...opts, headers });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new Error(typeof msg === 'string' ? msg : 'Request failed');
  }
  return data as T;
}

export const api = {
  register: (payload: {
    email: string;
    password: string;
    display_name: string;
    home_course?: string;
    handicap?: number;
  }) =>
    request<{ access_token: string; user: User }>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify(payload) },
      false,
    ),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      false,
    ),
  me: () => request<User>('/auth/me'),
  updateMe: (payload: Partial<User>) =>
    request<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(payload) }),

  feed: (scope: 'followers' | 'all' = 'followers') =>
    request<any[]>(`/feed?scope=${scope}`),
  createRound: (payload: any) => request<any>('/rounds', { method: 'POST', body: JSON.stringify(payload) }),
  getRound: (id: string) => request<any>(`/rounds/${id}`),
  deleteRound: (id: string) => request<any>(`/rounds/${id}`, { method: 'DELETE' }),
  toggleLike: (id: string) => request<{ liked: boolean; like_count: number }>(`/rounds/${id}/like`, { method: 'POST' }),
  getComments: (id: string) => request<any[]>(`/rounds/${id}/comments`),
  addComment: (id: string, text: string, mentions: string[] = []) =>
    request<any>(`/rounds/${id}/comments`, { method: 'POST', body: JSON.stringify({ text, mentions }) }),

  getUser: (id: string) => request<any>(`/users/${id}`),
  getUserRounds: (id: string) => request<any[]>(`/users/${id}/rounds`),
  getUserAchievements: (id: string) => request<{ total: number; achievements: any[] }>(`/users/${id}/achievements`),
  toggleFollow: (id: string) => request<{ following: boolean }>(`/users/${id}/follow`, { method: 'POST' }),

  discoverUsers: (q: string) => request<any[]>(`/discover/users?q=${encodeURIComponent(q)}`),
  discoverCourses: (q: string) => request<any[]>(`/discover/courses?q=${encodeURIComponent(q)}`),
  courseReviews: (name: string) => request<any[]>(`/courses/${encodeURIComponent(name)}/reviews`),
  courseRounds: (name: string) => request<any[]>(`/courses/${encodeURIComponent(name)}/rounds`),
  createReview: (payload: { course_name: string; rating: number; text: string }) =>
    request<any>('/courses/reviews', { method: 'POST', body: JSON.stringify(payload) }),
};
