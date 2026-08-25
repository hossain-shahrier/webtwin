import type {
  ApplicationCatalog,
  BusinessRule,
  CloneScorecard,
  EvaluationRun,
  Evidence,
  Investigation,
  InvestigationDetail,
  InvestigationTransition,
  ReferenceSystemContext,
  RuleProvenance,
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
  exploration_policy?: string;
  investigation_scope?: string;
  url_prefix?: string;
  start_url?: string;
  application_name?: string;
  application_key?: string;
  role_scope?: string;
  application_version?: string;
  environment?: string;
  spa_mode?: boolean;
  goal_spec?: {
    type: string;
    target: string;
    scope?: string | null;
    description?: string | null;
  } | null;
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

export function getRuleProvenance(id: string, ruleId: string): Promise<RuleProvenance> {
  return request(`/investigations/${id}/rules/${ruleId}/provenance`);
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

export function getAuthForm(id: string): Promise<{ form: import('./types').AuthFormSchema | null }> {
  return request(`/investigations/${id}/auth/form`);
}

export function submitAuthForm(
  id: string,
  payload: { values?: Record<string, string>; use_dummy?: boolean },
): Promise<{ id: string; status: string; use_dummy: boolean }> {
  return request(`/investigations/${id}/auth/submit-form`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function resumeFailedInvestigation(id: string): Promise<Investigation> {
  return request(`/investigations/${id}/resume`, { method: 'POST' });
}

export function restartFailedInvestigation(id: string): Promise<Investigation> {
  return request(`/investigations/${id}/restart`, { method: 'POST' });
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

export function exportCursorContext(id: string): Promise<{
  markdown: string;
  verified_rules: unknown[];
  candidate_rules: unknown[];
  reference_system?: ReferenceSystemContext;
  clone_spec_url?: string;
}> {
  return request(`/investigations/${id}/export/cursor`);
}

export function exportCloneSpec(id: string): Promise<Record<string, unknown>> {
  return request(`/investigations/${id}/export/clone-spec`);
}

export function exportPromptCapsules(id: string): Promise<{
  markdown: string;
  capsules: unknown[];
  skipped_without_evidence: string[];
  guidance: string[];
}> {
  return request(`/investigations/${id}/export/prompt-capsules`);
}

export function listAbsences(id: string): Promise<{
  absences: unknown[];
  count: number;
}> {
  return request(`/investigations/${id}/absences`);
}

export function planCounterfactual(
  id: string,
  body: {
    condition_field: string;
    condition_value: string;
    effect_field: string;
    expect_visible?: boolean | null;
    expect_required?: boolean | null;
    expect_enabled?: boolean | null;
    setup_fields?: Record<string, string>;
    operator?: string;
  },
): Promise<Record<string, unknown>> {
  return request(`/investigations/${id}/counterfactual`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function exportAiSpec(id: string): Promise<{
  markdown: string;
  summary: {
    screen_count?: number;
    layout_field_count?: number;
    interaction_field_count?: number;
    unique_interaction_field_count?: number;
    navigation_edge_count?: number;
    verified_rule_count?: number;
    candidate_rule_count?: number;
    absence_count?: number;
    link_coverage_pct?: number;
  };
  layout?: unknown[];
  route_groups?: unknown[];
  routes: unknown[];
  interactions: unknown[];
  navigation: unknown[];
  verified_rules: unknown[];
  candidate_rules: unknown[];
  absences?: unknown[];
  full_clone_spec_url?: string;
}> {
  return request(`/investigations/${id}/export/ai-spec`);
}

export function pinGoldenCatalog(applicationKey: string, version: string): Promise<Record<string, unknown>> {
  return request(`/applications/${encodeURIComponent(applicationKey)}/golden/${encodeURIComponent(version)}`, {
    method: 'POST',
  });
}

export function getReferenceSystem(id: string): Promise<ReferenceSystemContext> {
  return request(`/investigations/${id}/reference-system`);
}

export function getSiteGraph(id: string): Promise<{
  nodes: Array<{ id: string; name: string; visit_count?: number; primary_entity?: string | null }>;
  edges: Array<{ from: string; to: string | null; href: string; visited: boolean }>;
  visited_edges?: Array<{ from_screen_id: string; to_screen_id: string }>;
  stats?: Record<string, number>;
}> {
  return request(`/investigations/${id}/site-graph`);
}

export function getCloneScorecard(id: string): Promise<CloneScorecard> {
  return request(`/investigations/${id}/clone-scorecard`);
}

export function mergeInvestigationCatalog(id: string): Promise<{
  merged: boolean;
  catalog?: ApplicationCatalog;
}> {
  return request(`/investigations/${id}/merge-catalog`, { method: 'POST' });
}

export function getApplication(applicationKey: string): Promise<{
  catalog: ApplicationCatalog;
  investigations: Array<{
    id: string;
    goal: string;
    status: string;
    role_scope?: string | null;
    target_url: string;
  }>;
}> {
  return request(`/applications/${encodeURIComponent(applicationKey)}`);
}
