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

export interface AuthPauseMetadata {
  reason: AuthPauseReason;
  resume_allowed: boolean;
  detected_at: string;
  url?: string | null;
  message?: string | null;
}

export interface Investigation {
  id: string;
  goal: string;
  target_url: string;
  status: InvestigationStatus;
  application_name?: string | null;
  feature_scope?: string | null;
  auth_pause?: AuthPauseMetadata | null;
  failure_reason?: string | null;
  blocked_reason?: string | null;
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
