import { storage } from '@/src/utils/storage';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const ACCESS_KEY = 'teebox_access_v2';
const REFRESH_KEY = 'teebox_refresh_v2';

export type User = {
  id: string;
  email?: string;
  display_name: string;
  home_course?: string;
  handicap?: number | null;
  bio?: string;
  avatar?: string | null;
  is_admin?: boolean;
};

export type ImportJob = {
  id: string;
  kind: 'global' | 'country';
  country?: string;
  tile_deg?: number;
  status: 'queued' | 'running' | 'completed' | 'cancelled' | 'failed';
  total_tiles: number;
  processed_tiles: number;
  inserted: number;
  errors: number;
  total_courses_after?: number;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
  error?: string;
};

export async function saveTokens(access: string, refresh: string) {
  await storage.secureSet(ACCESS_KEY, access);
  await storage.secureSet(REFRESH_KEY, refresh);
}

export async function getAccessToken(): Promise<string | null> {
  const v = await storage.secureGet<string>(ACCESS_KEY, '');
  return v && typeof v === 'string' && v.length > 0 ? v : null;
}

export async function getRefreshToken(): Promise<string | null> {
  const v = await storage.secureGet<string>(REFRESH_KEY, '');
  return v && typeof v === 'string' && v.length > 0 ? v : null;
}

export async function clearTokens() {
  await storage.secureRemove(ACCESS_KEY);
  await storage.secureRemove(REFRESH_KEY);
}

// ------- Refresh queue: serialize concurrent refreshes so we never double-rotate -------
let refreshInFlight: Promise<string | null> | null = null;
let onAuthLostHandler: (() => void) | null = null;

export function setOnAuthLost(handler: () => void) {
  onAuthLostHandler = handler;
}

// Fetch with an abort-controller timeout. Prevents cold-start freezes when the
// backend is unreachable (offline / DNS / slow network) — a bare fetch() would
// hang forever and the app would sit on the splash screen indefinitely.
async function fetchWithTimeout(url: string, opts: RequestInit = {}, timeoutMs = 12000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function performRefresh(): Promise<string | null> {
  const rt = await getRefreshToken();
  if (!rt) return null;
  try {
    const res = await fetchWithTimeout(`${BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) throw new Error(`refresh failed ${res.status}`);
    const data = await res.json();
    await saveTokens(data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    await clearTokens();
    onAuthLostHandler?.();
    return null;
  }
}

function refreshAccess(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function request<T>(path: string, opts: RequestInit = {}, auth = true, _retry = false): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const token = await getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetchWithTimeout(`${BASE}/api${path}`, { ...opts, headers });
  if (res.status === 401 && auth && !_retry) {
    // Attempt a single refresh + retry
    const newAccess = await refreshAccess();
    if (newAccess) return request<T>(path, opts, auth, true);
  }
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
    request<{ access_token: string; refresh_token: string; user: User }>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify(payload) },
      false,
    ),
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      false,
    ),
  logout: async () => {
    const rt = await getRefreshToken();
    if (rt) {
      try {
        await fetch(`${BASE}/api/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        });
      } catch {}
    }
    await clearTokens();
  },
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
  getUserWishlist: (id: string) => request<any[]>(`/users/${id}/wishlist`),
  getUserFriends: (id: string) => request<any[]>(`/users/${id}/friends`),
  pinRound: (roundId: string) =>
    request<{ pinned: boolean; round_id: string }>(`/rounds/${roundId}/pin`, { method: 'POST' }),
  unpinRound: () => request<{ pinned: boolean }>(`/users/me/pin`, { method: 'DELETE' }),
  addWishlist: (course_name: string) =>
    request<{ added: boolean }>('/wishlist', { method: 'POST', body: JSON.stringify({ course_name }) }),
  removeWishlist: (course_name: string) =>
    request<{ removed: boolean }>(`/wishlist/${encodeURIComponent(course_name)}`, { method: 'DELETE' }),
  checkWishlist: (course_name: string) =>
    request<{ on_wishlist: boolean }>(`/wishlist/check/${encodeURIComponent(course_name)}`),
  toggleFollow: (id: string) => request<{ following: boolean }>(`/users/${id}/follow`, { method: 'POST' }),

  discoverUsers: (q: string) => request<any[]>(`/discover/users?q=${encodeURIComponent(q)}`),
  discoverCourses: (q: string) => request<any[]>(`/discover/courses?q=${encodeURIComponent(q)}`),
  courseReviews: (name: string) => request<any[]>(`/courses/${encodeURIComponent(name)}/reviews`),
  courseRounds: (name: string) => request<any[]>(`/courses/${encodeURIComponent(name)}/rounds`),
  courseInfo: (name: string) => request<any>(`/courses/${encodeURIComponent(name)}`),
  createReview: (payload: { course_name: string; rating: number; text: string }) =>
    request<any>('/courses/reviews', { method: 'POST', body: JSON.stringify(payload) }),

  // ---- Admin: bulk OSM course import ----
  adminCourseStats: () =>
    request<{ total_courses: number; by_source: Record<string, number>; supported_countries: string[] }>(
      '/admin/courses/stats',
    ),
  adminImportGlobal: (tile = 20, delay = 2) =>
    request<{ job_id: string; total_tiles: number; status: string }>(
      `/admin/courses/import-osm-global?tile=${tile}&delay=${delay}`,
      { method: 'POST' },
    ),
  adminImportCountry: (country: string, tile = 10, delay = 2) =>
    request<{ job_id: string; total_tiles: number; country: string; status: string }>(
      `/admin/courses/import-osm-country?country=${encodeURIComponent(country)}&tile=${tile}&delay=${delay}`,
      { method: 'POST' },
    ),
  adminGetJob: (id: string) => request<ImportJob>(`/admin/courses/import-jobs/${id}`),
  adminListJobs: () =>
    request<{ jobs: ImportJob[]; total_courses: number }>('/admin/courses/import-jobs'),
  adminCancelJob: (id: string) =>
    request<{ ok: boolean }>(`/admin/courses/import-jobs/${id}/cancel`, { method: 'POST' }),
};
