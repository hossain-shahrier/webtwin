import type {
  BusinessRule,
  EvaluationRun,
  Evidence,
  Investigation,
  InvestigationDetail,
  InvestigationTransition,
  SessionPublic,
  TimelineEvent,
} from './types';

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

export function createInvestigation(payload: {
  goal: string;
  target_url: string;
  feature_scope?: string;
  application_version?: string;
  environment?: string;
}): Promise<Investigation> {
  return request('/investigations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getInvestigationDetail(id: string): Promise<InvestigationDetail> {
  return request(`/investigations/${id}/detail`);
}

export function getTransitions(id: string): Promise<InvestigationTransition[]> {
  return request(`/investigations/${id}/transitions`);
}

export function getTimeline(id: string): Promise<TimelineEvent[]> {
  return request(`/investigations/${id}/timeline`);
}

export function getRules(id: string): Promise<BusinessRule[]> {
  return request(`/investigations/${id}/rules`);
}

export function getEvidence(id: string): Promise<Evidence[]> {
  return request(`/investigations/${id}/evidence`);
}

export function getMetrics(id: string): Promise<EvaluationRun[]> {
  return request(`/investigations/${id}/metrics`);
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

export function askQuestion(
  investigationId: string,
  question: string,
): Promise<{ answer: string; citations: Array<{ rule_id?: string; evidence_id?: string; confidence?: number }>; refused: boolean }> {
  return request(`/investigations/${investigationId}/questions`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}
