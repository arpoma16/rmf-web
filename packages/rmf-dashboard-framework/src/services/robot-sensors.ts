import { Authenticator } from './authenticator';

/**
 * Hand-written client for the api-server routes `/robots/platform` and `/robots/capabilities`
 * (see `docs/indra/robot-sensors.md`). The generated OpenAPI client does not know them, and it must
 * not be edited, so this one only does what it needs: a GET with the same `Bearer` token.
 */

export interface RobotCamera {
  name: string;
  /** Absolute ROS topic, e.g. `/bcr_bot_1/front_camera/image_raw`. */
  topic: string;
  kind: 'raw' | 'compressed';
}

export interface RobotCapabilities {
  fleet: string;
  /** Only the cameras that are publishing right now. */
  cameras: RobotCamera[];
  lidar_2d: boolean;
  lift: boolean;
  map: boolean;
  /** Names of declared sensors nobody publishes: cameras by name, plus `lidar_2d`, `lift`, `map`. */
  declared_but_missing: string[];
}

/** `true` platform up (carrying a cart), `false` down, `null` no lift or not reported yet. */
export type PlatformState = boolean | null;

const NON_CAMERA_SENSORS = ['lidar_2d', 'lift', 'map'];

/** The cameras that the fleet declares but the robot does not publish. */
export const missingCameras = (capabilities: RobotCapabilities): string[] =>
  capabilities.declared_but_missing.filter((name) => !NON_CAMERA_SENSORS.includes(name));

export interface RobotSensorsClient {
  getPlatform(): Promise<Record<string, PlatformState>>;
  getCapabilities(): Promise<Record<string, RobotCapabilities>>;
}

export class HttpRobotSensorsClient implements RobotSensorsClient {
  constructor(
    private apiServerUrl: string,
    private authenticator: Authenticator,
  ) {}

  private async _get<T>(path: string): Promise<T> {
    await this.authenticator.refreshToken();
    const token = this.authenticator.token;
    const response = await fetch(`${this.apiServerUrl.replace(/\/+$/, '')}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      throw new Error(`GET ${path} answered ${response.status}`);
    }
    return (await response.json()) as T;
  }

  async getPlatform(): Promise<Record<string, PlatformState>> {
    const body = await this._get<{ robots: Record<string, { lift_up: PlatformState }> }>(
      '/robots/platform',
    );
    return Object.fromEntries(
      Object.entries(body.robots).map(([name, state]) => [name, state.lift_up ?? null]),
    );
  }

  async getCapabilities(): Promise<Record<string, RobotCapabilities>> {
    return (await this._get<{ robots: Record<string, RobotCapabilities> }>('/robots/capabilities'))
      .robots;
  }
}
