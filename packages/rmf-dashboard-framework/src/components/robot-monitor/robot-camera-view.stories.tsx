import { Meta, StoryObj } from '@storybook/react-vite';

import { RobotCapabilities } from '../../services';
import { RobotCameraView } from './robot-camera-view';

export default {
  title: 'Robots/RobotCameraView',
  component: RobotCameraView,
  decorators: [
    (Story) => (
      <div style={{ width: 480, height: 360 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof RobotCameraView>;

type Story = StoryObj<typeof RobotCameraView>;

const capabilities = (overrides: Partial<RobotCapabilities> = {}): RobotCapabilities => ({
  fleet: 'bcr_bot',
  cameras: [{ name: 'front', topic: '/bcr_bot_1/front_camera/image_raw', kind: 'raw' }],
  lidar_2d: true,
  lift: true,
  map: true,
  declared_but_missing: [],
  ...overrides,
});

const base = { robotName: 'bcr_bot_1', webVideoUrl: 'http://localhost:8080' };

/** Needs `web_video_server` on :8080; without it the view ends in the error state. */
export const Streaming: Story = {
  args: { ...base, capabilities: capabilities(), capabilitiesLoaded: true },
};

export const AskingCapabilities: Story = {
  args: { ...base, capabilities: undefined, capabilitiesLoaded: false },
};

export const NoCamera: Story = {
  args: { ...base, capabilities: capabilities({ cameras: [] }), capabilitiesLoaded: true },
};

export const DeclaredButNotPublishing: Story = {
  args: {
    ...base,
    capabilities: capabilities({ cameras: [], declared_but_missing: ['front'] }),
    capabilitiesLoaded: true,
  },
};
