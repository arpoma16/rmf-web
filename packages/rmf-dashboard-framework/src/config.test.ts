import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAppSubtitle, getAppTitle, getLlmChatUrl } from './config';

describe('app config', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('uses the defaults when no env variable is set', () => {
    vi.stubEnv('VITE_APP_TITLE', '');
    vi.stubEnv('VITE_APP_SUBTITLE', '');
    vi.stubEnv('VITE_LLM_CHAT_URL', '');
    expect(getAppTitle()).toBe('Flota LINCE');
    expect(getAppSubtitle()).toBe('Monitorización de robots · Indra');
    expect(getLlmChatUrl()).toBe('http://localhost:4000/chat');
  });

  it('reads the title, subtitle and chat url from the env', () => {
    vi.stubEnv('VITE_APP_TITLE', 'Otra flota');
    vi.stubEnv('VITE_APP_SUBTITLE', 'Otro subtítulo');
    vi.stubEnv('VITE_LLM_CHAT_URL', 'http://gcs:9999/chat');
    expect(getAppTitle()).toBe('Otra flota');
    expect(getAppSubtitle()).toBe('Otro subtítulo');
    expect(getLlmChatUrl()).toBe('http://gcs:9999/chat');
  });
});
