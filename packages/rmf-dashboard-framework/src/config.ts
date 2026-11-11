/**
 * Operator-facing branding and external URLs. Single place to change them, either here or with
 * Vite env variables (e.g. in `.env.local`), without touching components.
 */
const DEFAULT_APP_TITLE = 'Flota LINCE';
const DEFAULT_APP_SUBTITLE = 'Monitorización de robots · Indra';
const DEFAULT_LLM_CHAT_URL = 'http://localhost:4000/chat';

// Read at call time so that tests can stub the env. Empty values fall back to the default.
const fromEnv = (value: string | undefined, fallback: string) => value || fallback;

export const getAppTitle = () => fromEnv(import.meta.env.VITE_APP_TITLE, DEFAULT_APP_TITLE);

export const getAppSubtitle = () =>
  fromEnv(import.meta.env.VITE_APP_SUBTITLE, DEFAULT_APP_SUBTITLE);

export const getLlmChatUrl = () =>
  fromEnv(import.meta.env.VITE_LLM_CHAT_URL, DEFAULT_LLM_CHAT_URL);

const WEB_VIDEO_PORT = 8080;

/**
 * Base URL of `web_video_server` (robot camera streams). `0.0.0.0` is where the server listens,
 * not an address for a browser, so by default use the host the dashboard was opened from.
 */
export const getWebVideoUrl = () =>
  fromEnv(
    import.meta.env.VITE_WEB_VIDEO_URL,
    `${window.location.protocol}//${window.location.hostname}:${WEB_VIDEO_PORT}`,
  );
