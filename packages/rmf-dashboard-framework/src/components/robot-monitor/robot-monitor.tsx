import { Close as CloseIcon } from '@mui/icons-material';
import { Alert, Box, IconButton, List, Tooltip, Typography } from '@mui/material';
import { TaskStateOutput as TaskState } from 'api-client';
import React from 'react';

import { getWebVideoUrl } from '../../config';
import { useAuthenticator, useRmfApi } from '../../hooks';
import {
  HttpRobotSensorsClient,
  PlatformState,
  RobotCapabilities,
  RobotSensorsClient,
} from '../../services';
import { AppEvents } from '../app-events';
import { RobotCameraView } from './robot-camera-view';
import { GRID_COLUMNS, MonitorRobot, RobotMonitorRow } from './robot-monitor-row';
import { usePolling } from './use-polling';

export const FLEETS_REFRESH_MS = 3000;
export const PLATFORM_REFRESH_MS = 2000;
/** Capabilities depend on the DDS discovery, so they are asked again, not once. */
export const CAPABILITIES_REFRESH_MS = 10000;

type Selection = [fleet: string, robot: string] | null;

export interface RobotMonitorProps {
  /** Defaults to one built from the api-server url and the authenticator of the dashboard. */
  sensorsClient?: RobotSensorsClient;
  /** Defaults to `VITE_WEB_VIDEO_URL`, or the host of the dashboard on port 8080. */
  webVideoUrl?: string;
}

const HEADERS = ['Robot', 'Estado', 'Batería', 'Plataforma', 'Tarea'];

export const RobotMonitor = ({ sensorsClient, webVideoUrl }: RobotMonitorProps) => {
  const rmfApi = useRmfApi();
  const authenticator = useAuthenticator();

  const client = React.useMemo<RobotSensorsClient>(
    () => sensorsClient ?? new HttpRobotSensorsClient(rmfApi.apiServerUrl ?? '', authenticator),
    [sensorsClient, rmfApi, authenticator],
  );

  const [robots, setRobots] = React.useState<MonitorRobot[]>([]);
  const [platform, setPlatform] = React.useState<Record<string, PlatformState>>({});
  const [capabilities, setCapabilities] = React.useState<Record<string, RobotCapabilities>>();
  const [selected, setSelected] = React.useState<Selection>(null);
  const [fleetsError, setFleetsError] = React.useState(false);

  // The selection can come from this list, from the robots table, from the tasks window or from
  // the map: all of them go through `AppEvents.robotSelect`.
  React.useEffect(() => {
    const sub = AppEvents.robotSelect.subscribe((data) => setSelected(data));
    return () => sub.unsubscribe();
  }, []);

  const fetchRobots = React.useCallback(async (): Promise<MonitorRobot[]> => {
    const fleets = (await rmfApi.fleetsApi.getFleetsFleetsGet()).data;
    const taskIds = fleets.flatMap((fleet) =>
      Object.values(fleet.robots ?? {}).flatMap((robot) => (robot.task_id ? [robot.task_id] : [])),
    );
    let tasks: Record<string, TaskState> = {};
    if (taskIds.length > 0) {
      try {
        const states = (await rmfApi.tasksApi.queryTaskStatesTasksGet(taskIds.join(','))).data;
        tasks = Object.fromEntries(states.map((task) => [task.booking.id, task]));
      } catch (e) {
        // the task is only a label: without it the id is shown
        console.warn('Robot monitor: could not read the tasks', e);
      }
    }
    return fleets.flatMap((fleet) =>
      Object.entries(fleet.robots ?? {}).map(([name, robot]) => ({
        fleet: fleet.name ?? '',
        name,
        status: robot.status ?? undefined,
        battery: robot.battery ?? undefined,
        task: robot.task_id ? (tasks[robot.task_id]?.category ?? robot.task_id) : undefined,
        decommissioned: robot.commission?.dispatch_tasks === false,
      })),
    );
  }, [rmfApi]);

  usePolling(
    fetchRobots,
    FLEETS_REFRESH_MS,
    (result) => {
      setRobots(result);
      setFleetsError(false);
    },
    () => setFleetsError(true),
  );

  const fetchPlatform = React.useCallback(() => client.getPlatform(), [client]);
  // a failed round keeps the last known value
  usePolling(fetchPlatform, PLATFORM_REFRESH_MS, setPlatform);

  const fetchCapabilities = React.useCallback(() => client.getCapabilities(), [client]);
  usePolling(fetchCapabilities, CAPABILITIES_REFRESH_MS, setCapabilities);

  const select = (robot: MonitorRobot) => {
    setSelected([robot.fleet, robot.name]);
    AppEvents.robotSelect.next([robot.fleet, robot.name]);
  };

  const deselect = () => {
    setSelected(null);
    AppEvents.robotSelect.next(null);
  };

  const selectedName = selected?.[1];

  return (
    <Box display="flex" flexDirection="column" height="100%" width="100%" minHeight={0}>
      {fleetsError && (
        <Alert severity="warning" role="alert">
          No se pudo leer la lista de robots.
        </Alert>
      )}
      <Box
        aria-hidden="true"
        sx={{
          display: 'grid',
          gridTemplateColumns: GRID_COLUMNS,
          columnGap: 2,
          px: 2,
          py: 0.5,
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        {HEADERS.map((header) => (
          <Typography key={header} variant="caption" color="text.secondary" fontWeight={700}>
            {header}
          </Typography>
        ))}
      </Box>
      <List
        role="listbox"
        aria-label="Robots"
        disablePadding
        sx={{ flex: '0 1 auto', maxHeight: '50%', overflowY: 'auto' }}
      >
        {robots.map((robot) => (
          <RobotMonitorRow
            key={`${robot.fleet}/${robot.name}`}
            robot={robot}
            platform={platform[robot.name]}
            selected={selected?.[0] === robot.fleet && selectedName === robot.name}
            onSelect={() => select(robot)}
          />
        ))}
        {robots.length === 0 && !fleetsError && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            Sin robots.
          </Typography>
        )}
      </List>
      <Box
        data-testid="robot-camera-panel"
        sx={{
          flex: 1,
          minHeight: 0,
          borderTop: 1,
          borderColor: 'divider',
          p: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
        }}
      >
        {selectedName ? (
          <>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Typography variant="subtitle2">Cámara de {selectedName}</Typography>
              <Tooltip title="Dejar de ver">
                <IconButton size="small" aria-label="dejar de ver" onClick={deselect}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
            <Box sx={{ flex: 1, minHeight: 0 }}>
              <RobotCameraView
                key={selectedName}
                robotName={selectedName}
                capabilities={capabilities?.[selectedName]}
                capabilitiesLoaded={capabilities !== undefined}
                webVideoUrl={webVideoUrl ?? getWebVideoUrl()}
              />
            </Box>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Elegí un robot para ver su cámara.
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default RobotMonitor;
