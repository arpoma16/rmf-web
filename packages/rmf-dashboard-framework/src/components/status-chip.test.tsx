import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { render } from '../utils/test-utils.test';
import { StatusChip } from './status-chip';

describe('StatusChip', () => {
  it('shows the status as text, so it is not communicated by color alone', () => {
    render(<StatusChip tone="success" data-testid="chip" label="ONLINE" />);
    expect(screen.getByTestId('chip').textContent).toBe('ONLINE');
  });

  it('renders every tone', () => {
    for (const tone of ['success', 'error', 'warning', 'neutral'] as const) {
      const { unmount } = render(<StatusChip tone={tone} label={tone} />);
      expect(screen.getByText(tone)).toBeTruthy();
      unmount();
    }
  });
});
