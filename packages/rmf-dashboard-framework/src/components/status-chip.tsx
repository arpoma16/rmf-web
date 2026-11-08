import { Box, Theme, useTheme } from '@mui/material';
import React from 'react';

export type StatusTone = 'success' | 'error' | 'warning' | 'neutral';

export interface StatusChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone: StatusTone;
  label: React.ReactNode;
}

const toneColors = (theme: Theme, tone: StatusTone) =>
  tone === 'neutral'
    ? { fg: theme.palette.text.secondary, bg: theme.palette.background.default }
    : { fg: theme.palette[tone].main, bg: theme.palette[tone].light };

/**
 * Pill with a dot and the status text. The colors come from the theme palette
 * (`success`, `error` and `warning` `main`/`light`), so changing the theme restyles every chip.
 */
export const StatusChip = ({ tone, label, ...otherProps }: StatusChipProps) => {
  const theme = useTheme();
  const { fg, bg } = toneColors(theme, tone);
  return (
    <Box
      component="span"
      {...otherProps}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 10px',
        borderRadius: '999px',
        backgroundColor: bg,
        color: fg,
        fontSize: 12,
        fontWeight: 700,
        lineHeight: 1.5,
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
      }}
    >
      <Box
        component="span"
        aria-hidden="true"
        sx={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'currentColor' }}
      />
      {label}
    </Box>
  );
};
