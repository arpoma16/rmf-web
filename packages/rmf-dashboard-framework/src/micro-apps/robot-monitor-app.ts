import { createMicroApp } from '../components';

export default createMicroApp(
  'robot-monitor',
  'Monitor de robots',
  () => import('../components/robot-monitor/robot-monitor'),
  () => ({}),
);
