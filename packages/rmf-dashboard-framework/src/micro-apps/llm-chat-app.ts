import { createMicroApp } from '../components';

export default createMicroApp(
  'llm-chat',
  'Chat LLM',
  () => import('../components/llm-chat/llm-chat'),
  () => ({}),
);
