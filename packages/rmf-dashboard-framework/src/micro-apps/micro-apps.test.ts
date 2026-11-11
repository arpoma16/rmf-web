import { describe, expect, it } from 'vitest';

import * as microApps from './index';

describe('micro-apps', () => {
  it('registers the LLM chat micro-app', () => {
    expect(microApps.llmChatApp.appId).toBe('llm-chat');
    expect(microApps.llmChatApp.displayName).toBe('Chat LLM');
  });

  it('registers the robot monitor micro-app', () => {
    expect(microApps.robotMonitorApp.appId).toBe('robot-monitor');
    expect(microApps.robotMonitorApp.displayName).toBe('Monitor de robots');
  });
});
