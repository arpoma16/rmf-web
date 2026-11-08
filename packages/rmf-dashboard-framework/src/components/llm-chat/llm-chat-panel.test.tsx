import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { render } from '../../utils/test-utils.test';
import { LlmChatPanel, LlmChatToggleButton } from './llm-chat-panel';

describe('LlmChatPanel', () => {
  it('keeps the iframe mounted while closed so the chat is not lost', () => {
    const { rerender } = render(<LlmChatPanel open={false} />);
    const iframe = screen.getByTitle('Chat LLM');
    expect(screen.getByTestId('llm-chat-panel').getAttribute('aria-hidden')).toBe('true');

    rerender(<LlmChatPanel open />);
    expect(screen.getByTitle('Chat LLM')).toBe(iframe);
    expect(screen.getByTestId('llm-chat-panel').getAttribute('aria-hidden')).toBe('false');

    rerender(<LlmChatPanel open={false} />);
    expect(screen.getByTitle('Chat LLM')).toBe(iframe);
  });
});

describe('LlmChatToggleButton', () => {
  it('calls onClick and reflects the open state', () => {
    const onClick = vi.fn();
    const { rerender } = render(<LlmChatToggleButton open={false} onClick={onClick} />);
    const button = screen.getByRole('button', { name: 'toggle llm chat' });
    expect(button.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(<LlmChatToggleButton open onClick={onClick} />);
    const pressed = screen.getByRole('button', { name: 'toggle llm chat' });
    expect(pressed.getAttribute('aria-pressed')).toBe('true');
  });
});
