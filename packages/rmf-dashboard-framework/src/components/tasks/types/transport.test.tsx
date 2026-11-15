import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  isTransportTaskDescriptionValid,
  makeDefaultTransportTaskDescription,
  makeTransportTaskBookingLabel,
  makeTransportTaskDescription,
  makeTransportTaskShortDescription,
  MAX_TRANSPORT_REPEAT,
  parseTransportTaskDescription,
  transportStations,
  TransportTaskDefinition,
  TransportTaskForm,
} from './transport';

// recogida_plain has no staging; recogida_orphan_staging has no centre; a charger is not a station.
const waypoints = [
  'cargador_1',
  'entrega_b',
  'entrega_b_staging',
  'recogida_a',
  'recogida_a_staging',
  'recogida_orphan_staging',
  'recogida_plain',
];

function activities(description: ReturnType<typeof makeTransportTaskDescription>) {
  return description.phases[0].activity.description.activities;
}

describe('Transport task', () => {
  it('only stations with a staging are offered, split by what they are for', () => {
    expect(transportStations(waypoints)).toEqual({
      pickups: ['recogida_a'],
      dropoffs: ['entrega_b'],
    });
  });

  it('the task goes to each staging, acts there, and does the same at the drop', () => {
    const description = makeTransportTaskDescription('recogida_a', 'entrega_b', 1);
    expect(description.category).toBe('transport_box');
    expect(activities(description)).toEqual([
      { category: 'go_to_place', description: 'recogida_a_staging' },
      {
        category: 'perform_action',
        description: {
          category: 'pick_box',
          description: { station: 'recogida_a' },
          unix_millis_action_duration_estimate: 60000,
          use_tool_sink: false,
        },
      },
      { category: 'go_to_place', description: 'entrega_b_staging' },
      {
        category: 'perform_action',
        description: {
          category: 'drop_box',
          description: { station: 'entrega_b' },
          unix_millis_action_duration_estimate: 60000,
          use_tool_sink: false,
        },
      },
    ]);
  });

  it('repeat chains whole cycles in ONE task, never two picks in a row', () => {
    const description = makeTransportTaskDescription('recogida_a', 'entrega_b', 3);
    expect(description.phases).toHaveLength(1);
    const steps = activities(description);
    expect(steps).toHaveLength(12);
    const actions = steps
      .filter((step) => step.category === 'perform_action')
      .map((step) => (step.description as { category: string }).category);
    expect(actions).toEqual([
      'pick_box',
      'drop_box',
      'pick_box',
      'drop_box',
      'pick_box',
      'drop_box',
    ]);
  });

  it('the form fields can be read back from the task description', () => {
    const description = makeTransportTaskDescription('recogida_a', 'entrega_b', 4);
    expect(parseTransportTaskDescription(description)).toEqual({
      pickup: 'recogida_a',
      dropoff: 'entrega_b',
      repeat: 4,
    });
    expect(parseTransportTaskDescription(makeDefaultTransportTaskDescription())).toEqual({
      pickup: '',
      dropoff: '',
      repeat: 1,
    });
  });

  it('the empty form is invalid, a filled one is valid, and the repeat has bounds', () => {
    expect(isTransportTaskDescriptionValid(makeDefaultTransportTaskDescription())).toBe(false);
    expect(isTransportTaskDescriptionValid(makeTransportTaskDescription('recogida_a', '', 1))).toBe(
      false,
    );
    expect(
      isTransportTaskDescriptionValid(makeTransportTaskDescription('recogida_a', 'entrega_b', 1)),
    ).toBe(true);
    expect(
      isTransportTaskDescriptionValid(
        makeTransportTaskDescription('recogida_a', 'entrega_b', MAX_TRANSPORT_REPEAT),
      ),
    ).toBe(true);
    for (const repeat of [0, -1, MAX_TRANSPORT_REPEAT + 1]) {
      expect(
        isTransportTaskDescriptionValid(
          makeTransportTaskDescription('recogida_a', 'entrega_b', repeat),
        ),
      ).toBe(false);
    }
  });

  it('booking label and short description say what it carries and where', () => {
    const description = makeTransportTaskDescription('recogida_a', 'entrega_b', 2);
    const label = makeTransportTaskBookingLabel(description);
    expect(label.task_definition_id).toBe(TransportTaskDefinition.taskDefinitionId);
    expect(label.destination).toBe('entrega_b');
    expect(makeTransportTaskShortDescription(description)).toBe(
      '[Transport] box from [recogida_a] to [entrega_b], [2] time/s',
    );
  });

  it('is a compose task, which is what RMF needs for actions', () => {
    expect(TransportTaskDefinition.requestCategory).toBe('compose');
  });

  it('TransportTaskForm offers the stations, builds the task and validates', () => {
    const onChange = vi.fn();
    const onValidate = vi.fn();
    render(
      <TransportTaskForm
        taskDesc={makeDefaultTransportTaskDescription()}
        patrolWaypoints={waypoints}
        onChange={onChange}
        onValidate={onValidate}
      />,
    );
    expect(onValidate).toHaveBeenCalledWith(false);

    const pickup = screen.getByTestId('transport-pickup');
    const input = within(pickup).getByLabelText(/pickup/i);
    pickup.focus();
    fireEvent.change(input, { target: { value: 'recogida' } });
    fireEvent.keyDown(pickup, { key: 'ArrowDown' });
    fireEvent.keyDown(pickup, { key: 'Enter' });

    expect(onChange).toHaveBeenCalled();
    const sent = onChange.mock.calls.at(-1)![0];
    expect(parseTransportTaskDescription(sent).pickup).toBe('recogida_a');
  });

  it('TransportTaskForm lists no charger and no station without a staging', () => {
    render(
      <TransportTaskForm
        taskDesc={makeDefaultTransportTaskDescription()}
        patrolWaypoints={waypoints}
        onChange={vi.fn()}
        onValidate={vi.fn()}
      />,
    );
    const pickup = screen.getByTestId('transport-pickup');
    const input = within(pickup).getByLabelText(/pickup/i);
    pickup.focus();
    fireEvent.keyDown(pickup, { key: 'ArrowDown' });
    const options = screen.queryAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual(['recogida_a']);
    expect(input).toBeTruthy();
  });

  it('changing the repeat rebuilds the task with that many cycles', () => {
    const onChange = vi.fn();
    render(
      <TransportTaskForm
        taskDesc={makeTransportTaskDescription('recogida_a', 'entrega_b', 1)}
        patrolWaypoints={waypoints}
        onChange={onChange}
        onValidate={vi.fn()}
      />,
    );
    const repeat = screen.getByLabelText(/times/i);
    fireEvent.change(repeat, { target: { value: '5' } });
    expect(onChange).toHaveBeenCalled();
    const sent = onChange.mock.calls.at(-1)![0];
    expect(parseTransportTaskDescription(sent)).toEqual({
      pickup: 'recogida_a',
      dropoff: 'entrega_b',
      repeat: 5,
    });
  });
});
