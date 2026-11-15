import { Autocomplete, Grid, TextField, useTheme } from '@mui/material';
import React from 'react';

import { PositiveIntField } from '../../form-inputs';
import { TaskBookingLabels } from '../booking-label';
import { TaskDefinition } from '../task-form';

/**
 * Transport of a box between two stations of the Indra factory: take it at a pickup station and
 * leave it at a dropoff station, optionally several times in ONE task.
 *
 * It is a compose task. RMF takes the robot to the staging of each station (so it plans the traffic)
 * and the fleet adapter does the rest of the station with an action:
 *
 *   go_to_place <pickup>_staging -> perform_action pick_box
 *   -> go_to_place <dropoff>_staging -> perform_action drop_box      (repeated `repeat` times)
 *
 * The same task `POST /indra/transport` of the api-server builds (api_server/indra_transport.py);
 * keep both in step.
 */
export const MAX_TRANSPORT_REPEAT = 50;
const ACTION_DURATION_ESTIMATE_MS = 60000;

export const TransportTaskDefinition: TaskDefinition = {
  taskDefinitionId: 'transport',
  taskDisplayName: 'Transport',
  requestCategory: 'compose',
  scheduleEventColor: undefined,
};

interface GoToPlaceActivity {
  category: 'go_to_place';
  description: string;
}

interface ActionActivity {
  category: 'perform_action';
  description: {
    category: string;
    description: { station: string };
    unix_millis_action_duration_estimate: number;
    use_tool_sink: boolean;
  };
}

export interface TransportTaskDescription {
  category: string;
  phases: [
    {
      activity: {
        category: string;
        description: { activities: (GoToPlaceActivity | ActionActivity)[] };
      };
    },
  ];
}

export interface TransportFields {
  pickup: string;
  dropoff: string;
  repeat: number;
}

const stagingOf = (station: string): string => (station ? `${station}_staging` : '');

const goToStaging = (station: string): GoToPlaceActivity => ({
  category: 'go_to_place',
  description: stagingOf(station),
});

const act = (category: string, station: string): ActionActivity => ({
  category: 'perform_action',
  description: {
    category,
    description: { station },
    unix_millis_action_duration_estimate: ACTION_DURATION_ESTIMATE_MS,
    use_tool_sink: false,
  },
});

/** The stations of the map: a `recogida_*` / `entrega_*` is one only if its `_staging` exists too. */
export function transportStations(waypoints: string[]): {
  pickups: string[];
  dropoffs: string[];
} {
  const names = new Set(waypoints);
  const stations = (prefix: string) =>
    waypoints
      .filter(
        (name) =>
          name.startsWith(prefix) && !name.endsWith('_staging') && names.has(stagingOf(name)),
      )
      .sort();
  return { pickups: stations('recogida_'), dropoffs: stations('entrega_') };
}

export function makeTransportTaskDescription(
  pickup: string,
  dropoff: string,
  repeat: number,
): TransportTaskDescription {
  const activities: (GoToPlaceActivity | ActionActivity)[] = [];
  for (let i = 0; i < repeat; i++) {
    activities.push(
      goToStaging(pickup),
      act('pick_box', pickup),
      goToStaging(dropoff),
      act('drop_box', dropoff),
    );
  }
  return {
    category: 'transport_box',
    phases: [{ activity: { category: 'sequence', description: { activities } } }],
  };
}

export function makeDefaultTransportTaskDescription(): TransportTaskDescription {
  return makeTransportTaskDescription('', '', 1);
}

/** The form has no state of its own: its fields are read back from the task description. */
export function parseTransportTaskDescription(desc: TransportTaskDescription): TransportFields {
  const activities = desc.phases[0].activity.description.activities;
  const stationOf = (index: number): string => {
    const activity = activities[index];
    return activity && activity.category === 'perform_action'
      ? activity.description.description.station
      : '';
  };
  return {
    pickup: stationOf(1),
    dropoff: stationOf(3),
    repeat: Math.floor(activities.length / 4),
  };
}

export function isTransportTaskDescriptionValid(desc: TransportTaskDescription): boolean {
  const { pickup, dropoff, repeat } = parseTransportTaskDescription(desc);
  return (
    pickup.length > 0 &&
    dropoff.length > 0 &&
    Number.isInteger(repeat) &&
    repeat >= 1 &&
    repeat <= MAX_TRANSPORT_REPEAT
  );
}

export function makeTransportTaskBookingLabel(desc: TransportTaskDescription): TaskBookingLabels {
  return {
    task_definition_id: TransportTaskDefinition.taskDefinitionId,
    destination: parseTransportTaskDescription(desc).dropoff,
  };
}

export function makeTransportTaskShortDescription(
  desc: TransportTaskDescription,
  displayName?: string,
): string {
  const { pickup, dropoff, repeat } = parseTransportTaskDescription(desc);
  return `[${displayName ?? TransportTaskDefinition.taskDisplayName}] box from [${pickup}] to [${dropoff}], [${repeat}] time/s`;
}

interface TransportTaskFormProps {
  taskDesc: TransportTaskDescription;
  /** Every named waypoint of the map: the stations are picked out of them. */
  patrolWaypoints: string[];
  onChange(transportTaskDescription: TransportTaskDescription): void;
  onValidate(valid: boolean): void;
}

export function TransportTaskForm({
  taskDesc,
  patrolWaypoints,
  onChange,
  onValidate,
}: TransportTaskFormProps): React.JSX.Element {
  const theme = useTheme();
  const { pickups, dropoffs } = React.useMemo(
    () => transportStations(patrolWaypoints),
    [patrolWaypoints],
  );
  const fields = parseTransportTaskDescription(taskDesc);

  const update = (changes: Partial<TransportFields>) => {
    const next = { ...fields, ...changes };
    const desc = makeTransportTaskDescription(next.pickup, next.dropoff, next.repeat);
    onValidate(isTransportTaskDescriptionValid(desc));
    onChange(desc);
  };

  React.useEffect(() => {
    onValidate(isTransportTaskDescriptionValid(taskDesc));
  }, [onValidate, taskDesc]);

  const station = (
    testId: string,
    label: string,
    options: string[],
    value: string,
    key: 'pickup' | 'dropoff',
  ) => (
    <Autocomplete
      data-testid={testId}
      fullWidth
      options={options}
      value={value || null}
      onChange={(_ev, newValue) => update({ [key]: newValue ?? '' })}
      renderInput={(params) => <TextField {...params} label={label} required />}
    />
  );

  return (
    <Grid container spacing={theme.spacing(2)} justifyContent="center" alignItems="center">
      <Grid item xs={6}>
        {station('transport-pickup', 'Pickup', pickups, fields.pickup, 'pickup')}
      </Grid>
      <Grid item xs={6}>
        {station('transport-dropoff', 'Dropoff', dropoffs, fields.dropoff, 'dropoff')}
      </Grid>
      <Grid item xs={4}>
        <PositiveIntField
          id="transport-repeat"
          label="Times"
          value={fields.repeat}
          onChange={(_ev, value) => update({ repeat: value })}
          error={fields.repeat < 1 || fields.repeat > MAX_TRANSPORT_REPEAT}
          helperText={`1 to ${MAX_TRANSPORT_REPEAT}`}
        />
      </Grid>
      <Grid item xs={8}>
        <TextField disabled fullWidth label="Load" value="Box" />
      </Grid>
    </Grid>
  );
}
