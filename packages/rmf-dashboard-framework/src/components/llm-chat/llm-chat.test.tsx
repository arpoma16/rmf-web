import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { render } from '../../utils/test-utils.test';
import { LlmChat } from './llm-chat';

describe('LlmChat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
  });

  it('points the iframe to the default chat url', () => {
    vi.stubEnv('VITE_LLM_CHAT_URL', '');
    render(<LlmChat />);
    expect(screen.getByTitle('Chat LLM').getAttribute('src')).toBe('http://localhost:4000/chat');
  });

  it('points the iframe to VITE_LLM_CHAT_URL', () => {
    vi.stubEnv('VITE_LLM_CHAT_URL', 'http://gcs:9999/chat');
    render(<LlmChat />);
    expect(screen.getByTitle('Chat LLM').getAttribute('src')).toBe('http://gcs:9999/chat');
  });

  it('shows a message and a link to a new tab when the chat does not load', () => {
    vi.stubEnv('VITE_LLM_CHAT_URL', 'http://gcs:9999/chat');
    render(<LlmChat />);
    expect(screen.queryByRole('alert')).toBeNull();
    act(() => {
      vi.advanceTimersByTime(20000);
    });
    expect(screen.getByRole('alert')).toBeTruthy();
    const link = screen.getByRole('link', { name: /abrir en pestaña nueva/i });
    expect(link.getAttribute('href')).toBe('http://gcs:9999/chat');
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('does not show the error once the iframe has loaded', () => {
    render(<LlmChat />);
    fireEvent.load(screen.getByTitle('Chat LLM'));
    act(() => {
      vi.advanceTimersByTime(20000);
    });
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
