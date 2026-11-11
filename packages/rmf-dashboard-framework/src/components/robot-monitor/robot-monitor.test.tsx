import { act, fireEvent, within } from '@testing-library/react';
import { ApiServerModelsRmfApiRobotStateStatus as Status } from 'api-client';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RmfApiProvider } from '../../hooks';
import { PlatformState, RobotCapabilities, RobotSensorsClient } from '../../services';
import { MockRmfApi, render, TestProviders } from '../../utils/test-utils.test';
import { AppEvents } from '../app-events';
import { makeRobot } from '../robots/test-utils.test';
import { buildStreamUrl, cameraAvailability, RobotCameraView } from './robot-camera-view';
import { RobotMonitor } from './robot-monitor';
import { platformLabel } from './robot-monitor-row';

const VIDEO = 'http://video:8080';

const frontCamera = {
  name: 'front',
  topic: '/bcr_bot_1/front_camera/image_raw',
  kind: 'raw' as const,
};

const caps = (overrides: Partial<RobotCapabilities> = {}): RobotCapabilities => ({
  fleet: 'bcr_bot',
  cameras: [frontCamera],
  lidar_2d: true,
  lift: true,
  map: true,
  declared_but_missing: [],
  ...overrides,
});

const setup = ({
  platform = { bcr_bot_1: false, bcr_bot_2: true, bcr_bot_3: null },
  capabilities = {
    bcr_bot_1: caps(),
    bcr_bot_2: caps({ cameras: [] }),
    bcr_bot_3: caps({ cameras: [], declared_but_missing: ['front', 'lift'] }),
  },
}: {
  platform?: Record<string, PlatformState>;
  capabilities?: Record<string, RobotCapabilities>;
} = {}) => {
  const rmfApi = new MockRmfApi();
  rmfApi.fleetsApi.getFleetsFleetsGet = vi.fn().mockResolvedValue({
    data: [
      {
        name: 'bcr_bot',
        robots: {
          bcr_bot_1: makeRobot({
            name: 'bcr_bot_1',
            battery: 0.87,
            status: Status.Working,
            task_id: 'task_1',
          }),
          bcr_bot_2: makeRobot({
            name: 'bcr_bot_2',
            battery: 0.1,
            status: Status.Idle,
            task_id: undefined,
          }),
          bcr_bot_3: makeRobot({
            name: 'bcr_bot_3',
            battery: 0.5,
            status: Status.Idle,
            task_id: undefined,
          }),
        },
      },
    ],
  });
  rmfApi.tasksApi.queryTaskStatesTasksGet = vi
    .fn()
    .mockResolvedValue({ data: [{ booking: { id: 'task_1' }, category: 'Transport cart' }] });
  const sensorsClient: RobotSensorsClient = {
    getPlatform: vi.fn().mockResolvedValue(platform),
    getCapabilities: vi.fn().mockResolvedValue(capabilities),
  };
  const root = render(
    <TestProviders>
      <RmfApiProvider value={rmfApi}>
        <RobotMonitor sensorsClient={sensorsClient} webVideoUrl={VIDEO} />
      </RmfApiProvider>
    </TestProviders>,
  );
  return { root, sensorsClient, rmfApi };
};

describe('buildStreamUrl', () => {
  it('builds the MJPEG url keeping the slashes of the topic', () => {
    expect(buildStreamUrl('http://host:8080', '/bcr_bot_1/front_camera/image_raw')).toBe(
      'http://host:8080/stream?topic=/bcr_bot_1/front_camera/image_raw&width=480&height=360&quality=60',
    );
  });

  it('drops the trailing slash of the base and omits missing size options', () => {
    expect(buildStreamUrl('http://host:8080/', '/r/cam', {})).toBe(
      'http://host:8080/stream?topic=/r/cam',
    );
  });

  it('escapes what is not a path character', () => {
    expect(buildStreamUrl('http://h', '/r/a b&c', {})).toBe('http://h/stream?topic=/r/a%20b%26c');
  });
});

describe('cameraAvailability', () => {
  it('is unknown until the capabilities arrive', () => {
    expect(cameraAvailability(undefined, false)).toEqual({ kind: 'unknown' });
  });

  it('is no-camera for a robot the api-server does not list', () => {
    expect(cameraAvailability(undefined, true)).toEqual({ kind: 'no-camera' });
  });

  it('is no-camera when nothing is declared', () => {
    expect(cameraAvailability(caps({ cameras: [] }), true)).toEqual({ kind: 'no-camera' });
  });

  it('only counts cameras, not other missing sensors, as declared-missing', () => {
    expect(
      cameraAvailability(caps({ cameras: [], declared_but_missing: ['lift', 'map'] }), true),
    ).toEqual({ kind: 'no-camera' });
    expect(
      cameraAvailability(caps({ cameras: [], declared_but_missing: ['front', 'lift'] }), true),
    ).toEqual({ kind: 'declared-missing', names: ['front'] });
  });

  it('is available with the first camera that publishes', () => {
    expect(cameraAvailability(caps(), true)).toEqual({ kind: 'available', camera: frontCamera });
  });
});

describe('platformLabel', () => {
  it('tells up, down and unknown apart', () => {
    expect(platformLabel(true)).toBe('SUBIDA');
    expect(platformLabel(false)).toBe('BAJADA');
    expect(platformLabel(null)).toBe('—');
    expect(platformLabel(undefined)).toBe('—');
  });
});

describe('RobotCameraView', () => {
  it('asks for the stream of the first published camera', () => {
    const root = render(
      <TestProviders>
        <RobotCameraView
          robotName="bcr_bot_1"
          capabilities={caps()}
          capabilitiesLoaded
          webVideoUrl={VIDEO}
        />
      </TestProviders>,
    );
    const img = root.getByRole('img', { hidden: true }) as HTMLImageElement;
    expect(img.getAttribute('src')).toBe(buildStreamUrl(VIDEO, frontCamera.topic));
    expect(root.getByRole('status', { name: 'cargando cámara' })).toBeTruthy();
  });

  it('shows the picture after the first frame and closes the stream on unmount', () => {
    const root = render(
      <TestProviders>
        <RobotCameraView
          robotName="bcr_bot_1"
          capabilities={caps()}
          capabilitiesLoaded
          webVideoUrl={VIDEO}
        />
      </TestProviders>,
    );
    const img = root.getByRole('img', { hidden: true }) as HTMLImageElement;
    fireEvent.load(img);
    expect(root.queryByRole('status', { name: 'cargando cámara' })).toBeNull();
    expect(root.getByRole('img')).toBeTruthy();

    root.unmount();
    expect(img.getAttribute('src')).toBe('');
  });

  it('shows an error with retry when the stream fails', () => {
    const root = render(
      <TestProviders>
        <RobotCameraView
          robotName="bcr_bot_1"
          capabilities={caps()}
          capabilitiesLoaded
          webVideoUrl={VIDEO}
        />
      </TestProviders>,
    );
    fireEvent.error(root.getByRole('img', { hidden: true }));
    expect(root.getByRole('alert').textContent).toContain('bcr_bot_1');
    fireEvent.click(root.getByRole('button', { name: 'Reintentar' }));
    expect(root.queryByRole('alert')).toBeNull();
  });

  it('gives up when no frame arrives in time', () => {
    vi.useFakeTimers();
    try {
      const root = render(
        <TestProviders>
          <RobotCameraView
            robotName="bcr_bot_1"
            capabilities={caps()}
            capabilitiesLoaded
            webVideoUrl={VIDEO}
          />
        </TestProviders>,
      );
      act(() => {
        vi.advanceTimersByTime(10001);
      });
      expect(root.getByRole('alert')).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not open any stream without a camera, with a missing one, or before knowing', () => {
    const states: [RobotCapabilities | undefined, boolean, RegExp][] = [
      [undefined, false, /Consultando/],
      [caps({ cameras: [] }), true, /no tiene cámara/],
      [caps({ cameras: [], declared_but_missing: ['front'] }), true, /no está publicando/],
    ];
    for (const [capabilities, loaded, text] of states) {
      const root = render(
        <TestProviders>
          <RobotCameraView
            robotName="bcr_bot_1"
            capabilities={capabilities}
            capabilitiesLoaded={loaded}
            webVideoUrl={VIDEO}
          />
        </TestProviders>,
      );
      expect(root.getByRole('status').textContent).toMatch(text);
      expect(root.queryByRole('img', { hidden: true })).toBeNull();
      root.unmount();
    }
  });
});

describe('RobotMonitor', () => {
  afterEach(() => {
    act(() => AppEvents.robotSelect.next(null));
  });

  it('lists the robots with fleet, status, battery, platform and task', async () => {
    const { root } = setup();
    const row1 = await root.findByTestId('robot-row-bcr_bot_1');
    await within(row1).findByText('Transport cart');

    expect(within(row1).getByText('bcr_bot')).toBeTruthy();
    expect(within(row1).getByTestId('robot-status').textContent).toBe('WORKING');
    expect(within(row1).getByTestId('robot-battery').textContent).toContain('87%');
    expect(within(row1).getByTestId('robot-platform').textContent).toBe('BAJADA');

    const row2 = root.getByTestId('robot-row-bcr_bot_2');
    expect(within(row2).getByTestId('robot-platform').textContent).toBe('SUBIDA');
    expect(within(row2).getByTestId('robot-status').textContent).toBe('IDLE');
    expect(within(row2).getByTestId('robot-task').textContent).toBe('—');

    const row3 = root.getByTestId('robot-row-bcr_bot_3');
    expect(within(row3).getByTestId('robot-platform').textContent).toBe('—');
  });

  it('selecting a robot shows its camera and emits robotSelect', async () => {
    const { root } = setup();
    const events: unknown[] = [];
    const sub = AppEvents.robotSelect.subscribe((e) => events.push(e));

    expect(root.getByText(/Elegí un robot/)).toBeTruthy();
    fireEvent.click(await root.findByTestId('robot-row-bcr_bot_1'));

    expect(events).toEqual([['bcr_bot', 'bcr_bot_1']]);
    const img = (await root.findByRole('img', { hidden: true })) as HTMLImageElement;
    expect(img.getAttribute('src')).toBe(buildStreamUrl(VIDEO, frontCamera.topic));
    expect(root.getByTestId('robot-row-bcr_bot_1').getAttribute('aria-selected')).toBe('true');
    sub.unsubscribe();
  });

  it('follows a robotSelect emitted by someone else (table, tasks or map)', async () => {
    const { root } = setup();
    await root.findByTestId('robot-row-bcr_bot_2');

    act(() => AppEvents.robotSelect.next(['bcr_bot', 'bcr_bot_2']));

    expect(root.getByTestId('robot-row-bcr_bot_2').getAttribute('aria-selected')).toBe('true');
    expect(root.getByTestId('robot-row-bcr_bot_1').getAttribute('aria-selected')).toBe('false');
    expect(await root.findByText(/no tiene cámara/)).toBeTruthy();
  });

  it('keeps one stream at a time: switching robots closes the previous one', async () => {
    const { root } = setup({
      capabilities: {
        bcr_bot_1: caps(),
        bcr_bot_2: caps({
          cameras: [{ name: 'front', topic: '/bcr_bot_2/front_camera/image_raw', kind: 'raw' }],
        }),
        bcr_bot_3: caps(),
      },
    });
    fireEvent.click(await root.findByTestId('robot-row-bcr_bot_1'));
    const first = (await root.findByRole('img', { hidden: true })) as HTMLImageElement;

    fireEvent.click(root.getByTestId('robot-row-bcr_bot_2'));

    expect(first.getAttribute('src')).toBe('');
    const images = root.getAllByRole('img', { hidden: true }) as HTMLImageElement[];
    expect(images).toHaveLength(1);
    expect(images[0].getAttribute('src')).toBe(
      buildStreamUrl(VIDEO, '/bcr_bot_2/front_camera/image_raw'),
    );
  });

  it('shows "declared but not publishing" for a robot whose camera is missing', async () => {
    const { root } = setup();
    fireEvent.click(await root.findByTestId('robot-row-bcr_bot_3'));
    expect(await root.findByText(/no está publicando/)).toBeTruthy();
    expect(root.queryByRole('img', { hidden: true })).toBeNull();
  });

  it('stops watching: closes the stream and emits null', async () => {
    const { root } = setup();
    const events: unknown[] = [];
    const sub = AppEvents.robotSelect.subscribe((e) => events.push(e));
    fireEvent.click(await root.findByTestId('robot-row-bcr_bot_1'));
    const img = (await root.findByRole('img', { hidden: true })) as HTMLImageElement;

    fireEvent.click(root.getByRole('button', { name: 'dejar de ver' }));

    expect(events.at(-1)).toBeNull();
    expect(img.getAttribute('src')).toBe('');
    expect(root.getByText(/Elegí un robot/)).toBeTruthy();
    sub.unsubscribe();
  });

  it('refreshes the capabilities periodically, not just once', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { root, sensorsClient } = setup();
      await root.findByTestId('robot-row-bcr_bot_1');
      expect(sensorsClient.getCapabilities).toHaveBeenCalledTimes(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10100);
      });
      expect(
        (sensorsClient.getCapabilities as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThanOrEqual(2);
      expect(
        (sensorsClient.getPlatform as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThanOrEqual(5);
    } finally {
      vi.useRealTimers();
    }
  });
});
