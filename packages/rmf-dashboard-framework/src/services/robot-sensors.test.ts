import { afterEach, describe, expect, it, vi } from 'vitest';

import { HttpRobotSensorsClient, missingCameras, RobotCapabilities } from './robot-sensors';
import { StubAuthenticator } from './stub-authenticator';

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);

describe('HttpRobotSensorsClient', () => {
  const authenticator = new StubAuthenticator();

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('asks for the platform with the bearer token and flattens lift_up', async () => {
    const fetchMock = vi.fn().mockReturnValue(
      jsonResponse({
        robots: { a: { lift_up: true }, b: { lift_up: false }, c: { lift_up: null } },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = new HttpRobotSensorsClient('http://api:8000/', authenticator);
    expect(await client.getPlatform()).toEqual({ a: true, b: false, c: null });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api:8000/robots/platform');
    expect(init.headers.Authorization).toBe(`Bearer ${authenticator.token}`);
  });

  it('returns the capabilities by robot', async () => {
    const caps: RobotCapabilities = {
      fleet: 'bcr_bot',
      cameras: [{ name: 'front', topic: '/bcr_bot_1/front_camera/image_raw', kind: 'raw' }],
      lidar_2d: true,
      lift: true,
      map: true,
      declared_but_missing: [],
    };
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(jsonResponse({ robots: { bcr_bot_1: caps } })));

    const client = new HttpRobotSensorsClient('http://api:8000', authenticator);
    expect(await client.getCapabilities()).toEqual({ bcr_bot_1: caps });
  });

  it('rejects when the api-server answers an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(jsonResponse({}, 401)));
    const client = new HttpRobotSensorsClient('http://api:8000', authenticator);
    await expect(client.getPlatform()).rejects.toThrow('401');
  });
});

describe('missingCameras', () => {
  it('keeps the cameras and drops the other sensors', () => {
    const caps = {
      declared_but_missing: ['rear', 'lift', 'lidar_2d', 'map'],
    } as RobotCapabilities;
    expect(missingCameras(caps)).toEqual(['rear']);
  });
});
