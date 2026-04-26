/**
 * Deprecated compatibility shell.
 *
 * Do not add endpoint wrappers here.
 * Import explicit API modules instead:
 * - @shared/api/modules/projects
 * - @shared/api/modules/threads
 * - @shared/api/modules/auth
 * - @shared/api/modules/members
 * - @shared/api/modules/clients
 * - @shared/api/modules/knowledge
 *
 * Import transport/session core from:
 * - @shared/api/core/openapi
 * - @shared/api/core/http
 * - @shared/api/core/session
 * - @shared/api/core/stream
 * - @shared/api/core/errors
 */
export { client } from './core/openapi';
export { streamFetch } from './core/stream';
export {
  clearSessionToken,
  getSessionToken,
  handleUnauthorizedResponse,
  setSessionToken,
} from './core/session';
export { getErrorMessage } from './core/errors';

export type {
  ProjectChannelResponse,
  ProjectChannelUpsert,
  ProjectConfigurationResponse,
  ProjectIntegrationResponse,
  ProjectIntegrationUpsert,
  ProjectLimitProfileUpdate,
  ProjectPoliciesUpdate,
  ProjectResponse,
  ProjectSettingsUpdate,
} from './modules/projectTypes';
