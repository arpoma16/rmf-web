import { Chat as ChatIcon } from '@mui/icons-material';
import { Box, IconButton, Tooltip } from '@mui/material';

import { LlmChat } from './llm-chat';

export const LLM_CHAT_PANEL_WIDTH = '26rem';

export interface LlmChatPanelProps {
  open: boolean;
  /** Distance from the top of the viewport that is already taken by the app bar. */
  top?: string;
  /** Defaults to `VITE_LLM_CHAT_URL`, or `http://localhost:4000/chat`. */
  url?: string;
}

/**
 * Side panel docked on the right. It is always mounted and is only collapsed when closed, so the
 * iframe is never reloaded and the conversation survives toggling and changing tabs.
 */
export const LlmChatPanel = ({ open, top = '0px', url }: LlmChatPanelProps) => (
  <Box
    data-testid="llm-chat-panel"
    aria-hidden={!open}
    sx={{
      position: 'sticky',
      top,
      alignSelf: 'flex-start',
      flexShrink: 0,
      height: `calc(100vh - ${top})`,
      width: open ? LLM_CHAT_PANEL_WIDTH : 0,
      overflow: 'hidden',
      borderLeft: open ? 1 : 0,
      borderColor: 'divider',
      transition: 'width 150ms ease',
    }}
  >
    {/* fixed inner width so the chat does not reflow while the panel animates */}
    <Box sx={{ width: LLM_CHAT_PANEL_WIDTH, height: '100%' }}>
      <LlmChat url={url} />
    </Box>
  </Box>
);

export interface LlmChatToggleButtonProps {
  open: boolean;
  onClick: () => void;
}

export const LlmChatToggleButton = ({ open, onClick }: LlmChatToggleButtonProps) => (
  <Tooltip title="Chat LLM">
    <IconButton
      size="large"
      color="inherit"
      aria-label="toggle llm chat"
      aria-pressed={open}
      onClick={onClick}
    >
      <ChatIcon />
    </IconButton>
  </Tooltip>
);
