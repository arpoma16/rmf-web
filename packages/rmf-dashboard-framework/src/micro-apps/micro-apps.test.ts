import { describe, expect, it } from 'vitest';

import * as microApps from './index';

describe('micro-apps', () => {
  it('registers the LLM chat micro-app', () => {
    expect(microApps.llmChatApp.appId).toBe('llm-chat');
    expect(microApps.llmChatApp.displayName).toBe('Chat LLM');
  });
});
