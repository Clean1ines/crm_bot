import createClient from 'openapi-fetch';

import type { paths } from '../generated/schema';
import { createTimeoutMiddleware } from '../fetchWithTimeout';
import { t } from '../../i18n';
import { API_BASE_URL } from './config';
import { getErrorMessage, showErrorToast } from './errors';
import { getSessionToken, handleUnauthorizedResponse, isUnauthorized } from './session';

export const client = createClient<paths>({
  baseUrl: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

client.use({
  onRequest({ request }) {
    const token = getSessionToken();

    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`);
    }

    return request;
  },
});

client.use({
  onResponse({ response }) {
    if (isUnauthorized(response)) {
      const hadSession = handleUnauthorizedResponse();

      if (hadSession) {
        showErrorToast(t('api.error.sessionExpired'));
      }

      return response;
    }

    if (!response.ok) {
      return response
        .clone()
        .json()
        .then((errData) => {
          showErrorToast(getErrorMessage(errData));
          return response;
        })
        .catch(() => {
          const message = response.status >= 500 && response.status < 600
            ? t('api.error.serverUnavailable')
            : t('api.error.httpStatus', {
                status: response.status,
                statusText: response.statusText,
              });

          showErrorToast(message);
          return response;
        });
    }

    return response;
  },
});

client.use(createTimeoutMiddleware(30000));
