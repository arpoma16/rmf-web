import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAppSubtitle, getAppTitle, getLlmChatUrl, getWebVideoUrl } from './config';

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

  it('serves the robot video from the host of the dashboard, port 8080, by default', () => {
    vi.stubEnv('VITE_WEB_VIDEO_URL', '');
    expect(getWebVideoUrl()).toBe(`http://${window.location.hostname}:8080`);
  });

  it('reads the video server url from the env', () => {
    vi.stubEnv('VITE_WEB_VIDEO_URL', 'http://video:9000');
    expect(getWebVideoUrl()).toBe('http://video:9000');
  });
});
