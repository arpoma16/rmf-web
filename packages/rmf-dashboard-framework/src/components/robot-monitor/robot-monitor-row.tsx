import { Box, LinearProgress, ListItemButton, Typography } from '@mui/material';
import { ApiServerModelsRmfApiRobotStateStatus as Status } from 'api-client';

import { PlatformState } from '../../services';
import { robotStatusToUpperCase } from '../robots/utils';
import { StatusChip, StatusTone } from '../status-chip';

export interface MonitorRobot {
  fleet: string;
  name: string;
  status?: Status;
  /** 0..1 */
  battery?: number;
  /** Task label, or `undefined` when the robot has none. */
  task?: string;
  decommissioned?: boolean;
}

export const GRID_COLUMNS = 'minmax(0, 1.4fr) auto minmax(0, 1fr) auto minmax(0, 1.2fr)';

export const statusTone = (robot: MonitorRobot): StatusTone => {
  if (robot.decommissioned) return 'neutral';
  switch (robot.status) {
    case Status.Error:
      return 'error';
    case Status.Offline:
    case Status.Uninitialized:
      return 'neutral';
    case Status.Working:
      return 'success';
    default:
      return 'warning';
  }
};

export const platformLabel = (state: PlatformState | undefined): string =>
  state === true ? 'SUBIDA' : state === false ? 'BAJADA' : '—';

export interface RobotMonitorRowProps {
  robot: MonitorRobot;
  platform: PlatformState | undefined;
  selected: boolean;
  onSelect: () => void;
}

export const RobotMonitorRow = ({ robot, platform, selected, onSelect }: RobotMonitorRowProps) => {
  const percent = robot.battery === undefined ? undefined : Math.round(robot.battery * 100);
  return (
    <ListItemButton
      role="option"
      aria-selected={selected}
      selected={selected}
      onClick={onSelect}
      data-testid={`robot-row-${robot.name}`}
      sx={{
        display: 'grid',
        gridTemplateColumns: GRID_COLUMNS,
        columnGap: 2,
        alignItems: 'center',
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" fontWeight={700} noWrap>
          {robot.name}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap>
          {robot.fleet}
        </Typography>
      </Box>
      <StatusChip
        data-testid="robot-status"
        tone={statusTone(robot)}
        label={
          robot.decommissioned
            ? 'DECOMMISSIONED'
            : robot.status
              ? robotStatusToUpperCase(robot.status)
              : 'UNKNOWN'
        }
      />
      <Box data-testid="robot-battery" sx={{ minWidth: 0 }}>
        <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {percent === undefined ? '—' : `${percent}%`}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={percent ?? 0}
          color={percent !== undefined && percent < 20 ? 'error' : 'primary'}
          aria-label={`batería de ${robot.name}`}
        />
      </Box>
      <Typography
        variant="caption"
        fontWeight={700}
        data-testid="robot-platform"
        title="Plataforma elevable"
      >
        {platformLabel(platform)}
      </Typography>
      <Typography variant="caption" color="text.secondary" noWrap data-testid="robot-task">
        {robot.task ?? '—'}
      </Typography>
    </ListItemButton>
  );
};
