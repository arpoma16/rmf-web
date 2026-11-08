import { Alert, Box, Link } from '@mui/material';
import React from 'react';

import { getLlmChatUrl } from '../../config';

// A refused connection does not always fire `error` on an iframe, so also give up after a while.
const LOAD_TIMEOUT_MS = 10000;

export interface LlmChatProps {
  /** Defaults to `VITE_LLM_CHAT_URL`, or `http://localhost:4000/chat`. */
  url?: string;
}

export const LlmChat = ({ url }: LlmChatProps) => {
  const chatUrl = url || getLlmChatUrl();
  const [status, setStatus] = React.useState<'loading' | 'loaded' | 'failed'>('loading');

  React.useEffect(() => {
    setStatus('loading');
    const timer = setTimeout(
      () => setStatus((prev) => (prev === 'loading' ? 'failed' : prev)),
      LOAD_TIMEOUT_MS,
    );
    return () => clearTimeout(timer);
  }, [chatUrl]);

  return (
    <Box display="flex" flexDirection="column" height="100%" width="100%">
      {status === 'failed' && (
        <Alert severity="warning" role="alert">
          No se pudo cargar el chat del LLM.{' '}
          <Link href={chatUrl} target="_blank" rel="noopener noreferrer">
            Abrir en pestaña nueva
          </Link>
        </Alert>
      )}
      <Box
        component="iframe"
        title="Chat LLM"
        src={chatUrl}
        onLoad={() => setStatus('loaded')}
        onError={() => setStatus('failed')}
        sx={{ flex: 1, border: 0, width: '100%', minHeight: 0 }}
      />
    </Box>
  );
};

export default LlmChat;
