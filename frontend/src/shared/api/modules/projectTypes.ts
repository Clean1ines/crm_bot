import type { components } from '../generated/schema';

export type ProjectResponse = components['schemas']['ProjectResponse'];
export type ProjectConfigurationResponse = components['schemas']['ProjectConfigurationResponse'];
export type ProjectIntegrationResponse = components['schemas']['ProjectIntegrationResponse'];
export type ProjectChannelResponse = components['schemas']['ProjectChannelResponse'];

export type ProjectCreate = components['schemas']['ProjectCreate'];
export type ProjectUpdate = components['schemas']['ProjectUpdate'];
export type BotTokenRequest = components['schemas']['BotTokenRequest'];
export type ManagerAddRequest = components['schemas']['ManagerAddRequest'];

export type ProjectSettingsUpdate = {
  brand_name?: string;
  industry?: string;
  tone_of_voice?: string;
  default_language?: string;
  default_timezone?: string;
  system_prompt_override?: string;
};

export type ProjectPoliciesUpdate = {
  escalation_policy_json?: Record<string, unknown>;
  routing_policy_json?: Record<string, unknown>;
  crm_policy_json?: Record<string, unknown>;
  response_policy_json?: Record<string, unknown>;
  privacy_policy_json?: Record<string, unknown>;
};

export type ProjectLimitProfileUpdate = {
  monthly_token_limit?: number;
  requests_per_minute?: number;
  max_concurrent_threads?: number;
  priority?: number;
  fallback_model?: string;
};

export type ProjectIntegrationUpsert = {
  provider: string;
  status?: string;
  config_json?: Record<string, unknown>;
  credentials_encrypted?: string;
};

export type ProjectChannelUpsert = {
  kind: 'platform' | 'client' | 'manager' | 'widget';
  provider: string;
  status?: string;
  config_json?: Record<string, unknown>;
};
