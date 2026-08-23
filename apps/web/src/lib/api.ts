import type { Investigation, InvestigationDetail, InvestigationTransition, SessionPublic } from './types';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8060';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listInvestigations(): Promise<Investigation[]> {
  return request('/investigations');
}

export function getInvestigationDetail(id: string): Promise<InvestigationDetail> {
  return request(`/investigations/${id}/detail`);
}

export function getTransitions(id: string): Promise<InvestigationTransition[]> {
  return request(`/investigations/${id}/transitions`);
}

export function beginAuthentication(id: string): Promise<SessionPublic> {
  return request(`/investigations/${id}/auth/begin`, { method: 'POST' });
}

export function markAuthenticationReady(id: string): Promise<SessionPublic> {
  return request(`/investigations/${id}/auth/mark-ready`, { method: 'POST' });
}

export function resumeAfterAuthentication(id: string): Promise<Investigation> {
  return request(`/investigations/${id}/auth/resume`, { method: 'POST' });
}

export function resumeFailedInvestigation(id: string): Promise<Investigation> {
  return request(`/investigations/${id}/resume`, { method: 'POST' });
}
