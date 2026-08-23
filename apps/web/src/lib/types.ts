export type InvestigationStatus =
  | 'created'
  | 'initializing'
  | 'auth_check'
  | 'auth_required'
  | 'authenticated'
  | 'exploring'
  | 'observing'
  | 'generating_rule'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'cancelled';

export type SessionStatus =
  | 'not_started'
  | 'auth_required'
  | 'authenticating'
  | 'authenticated'
  | 'expired'
  | 'failed';

export type AuthPauseReason =
  | 'login_required'
  | 'mfa_required'
  | 'captcha'
  | 'cloudflare'
  | 'session_expired';

export interface AuthFormField {
  key: string;
  label: string;
  input_type: string;
  required: boolean;
  selector: string;
  selector_candidates?: string[];
  name?: string | null;
  placeholder?: string | null;
  options?: string[];
  autocomplete?: string | null;
  is_secret: boolean;
}

export interface AuthFormSchema {
  page_kind: string;
  url?: string | null;
  title?: string | null;
  form_selector?: string | null;
  fields: AuthFormField[];
  submit_label?: string | null;
  supports_dummy: boolean;
  notes?: string[];
}

export interface AuthPauseMetadata {
  reason: AuthPauseReason;
  resume_allowed: boolean;
  detected_at: string;
  url?: string | null;
  message?: string | null;
  form?: AuthFormSchema | null;
}

export interface Investigation {
  id: string;
  goal: string;
  target_url: string;
  status: InvestigationStatus;
  application_name?: string | null;
  application_key?: string | null;
  feature_scope?: string | null;
  exploration_policy?: string | null;
  investigation_scope?: string | null;
  url_prefix?: string | null;
  start_url?: string | null;
  role_scope?: string | null;
  environment?: string | null;
  spa_mode?: boolean;
  auth_pause?: AuthPauseMetadata | null;
  failure_reason?: string | null;
  blocked_reason?: string | null;
  checkpoint?: { status: InvestigationStatus; target_url: string } | null;
  created_at: string;
  updated_at: string;
}

export interface SessionPublic {
  id: string;
  investigation_id: string;
  auth_state: string;
  session_status: SessionStatus;
  has_persisted_storage: boolean;
  human_ready: boolean;
  auth_verified: boolean;
  checkpoint_status?: InvestigationStatus | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationDetail {
  investigation: Investigation;
  session?: SessionPublic | null;
}

export interface InvestigationTransition {
  id: string;
  investigation_id: string;
  from_status: InvestigationStatus;
  to_status: InvestigationStatus;
  event: string;
  reason?: string | null;
  occurred_at: string;
}

export interface TimelineEvent {
  id: string;
  investigation_id: string;
  type: string;
  description: string;
  occurred_at: string;
}

export interface BusinessRule {
  id: string;
  investigation_id: string;
  name: string;
  status: string;
  confidence: number;
  condition: { field: string; operator: string; value?: string | number | boolean | null };
  effect: { field: string; visible?: boolean | null; required?: boolean | null };
  evidence_ids: string[];
  verification_run_ids?: string[];
}

export interface RuleProvenance {
  rule: BusinessRule;
  evidence: Evidence[];
  experiments: Array<{
    id: string;
    rule_id: string;
    status: string;
    confidence: number;
    results: Array<{ passed: boolean; details: string }>;
  }>;
}

export interface Evidence {
  id: string;
  investigation_id: string;
  type: string;
  sensitivity: string;
  confidence: number;
  url?: string | null;
  content_hash?: string | null;
  payload: Record<string, unknown>;
  captured_at: string;
}

export interface EvaluationRun {
  id: string;
  investigation_id: string;
  policy: string;
  exploration_coverage: number;
  state_coverage: number;
  actions_taken: number;
  candidate_rules: number;
  verified_rules: number;
  rules_per_action: number;
  safety_violations: number;
  blocked_unsafe_actions: number;
  pages_seen: number;
  discovery_f1?: number | null;
  settle_timeouts?: number;
  soft_nav_success_rate?: number | null;
  routes_seen?: number;
  created_at: string;
}

export interface ReferenceSystemScreen {
  id: string;
  name: string;
  url: string;
  path: string;
  visit_count: number;
  form_count: number;
  field_count: number;
  primary_entity?: string | null;
  entity_names?: string[];
  fields: Array<{
    name: string;
    label?: string | null;
    input_type?: string | null;
    required?: boolean;
    visible?: boolean;
    entity?: string | null;
  }>;
}

export interface ReferenceSystemNavigation {
  from_screen_id: string;
  to_screen_id: string;
  trigger: string;
  event_type: string;
}

export interface ReferenceSystemFlow {
  name: string;
  confidence: number;
  screen_ids?: string[];
  entity_names?: string[];
  steps: Array<{ order: number; description: string; screen_id?: string | null }>;
}

export interface DomainEntity {
  name: string;
  confidence: number;
  field_count: number;
  screen_ids: string[];
  fields: Array<{ field: string; label?: string | null; screen_id?: string | null }>;
  rule_names: string[];
}

export interface RoleSystemMap {
  role_scope: string;
  screen_count: number;
  entity_names: string[];
  flow_names: string[];
  navigation_count: number;
  verified_rule_names: string[];
  candidate_rule_names: string[];
  investigation_ids: string[];
  summary: string;
}

export interface ApplicationCatalog {
  application_key: string;
  application_name?: string | null;
  target_hosts: string[];
  entities: DomainEntity[];
  roles: Record<string, RoleSystemMap>;
  investigation_ids: string[];
  updated_at: string;
}

export interface ReferenceSystemContext {
  investigation_id: string;
  application_name?: string | null;
  application_key?: string | null;
  target_url: string;
  role_scope?: string | null;
  environment?: string | null;
  application_version?: string | null;
  feature_scope?: string | null;
  framework_hints: Record<string, unknown>;
  entities: DomainEntity[];
  screens: ReferenceSystemScreen[];
  navigation: ReferenceSystemNavigation[];
  flows: ReferenceSystemFlow[];
  rules_by_screen: Array<{
    screen_id: string;
    verified: string[];
    candidate: string[];
  }>;
  role_map?: RoleSystemMap | null;
  catalog?: ApplicationCatalog | null;
  related_roles?: string[];
  summary: string;
  exploration_coverage?: number;
  unexplored_fields?: string[];
  discovered_links?: unknown[];
  site_graph_stats?: {
    total_discovered?: number;
    total_internal?: number;
    total_visited_links?: number;
    coverage_pct?: number;
    unvisited_sample?: string[];
  };
  clone_scorecard?: CloneScorecard;
}

export interface CloneScorecard {
  verified_rules: number;
  candidate_rules: number;
  contradicted_rules: number;
  exploration_coverage: number;
  unknown_fields: number;
  screen_count: number;
  field_count: number;
  fields_with_selectors: number;
  discovered_pages?: number;
  visited_pages?: number;
  link_coverage_pct?: number;
  export_completeness: number;
  clone_ready: boolean;
  gaps: string[];
}
