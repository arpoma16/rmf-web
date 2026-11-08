import { Box, Button } from '@mui/material';
import {
  DataGrid,
  GridCellParams,
  GridColDef,
  GridEventListener,
  GridRowParams,
  GridValueGetterParams,
  MuiEvent,
} from '@mui/x-data-grid';
import { DoorMode, DoorState } from 'api-client';
import React from 'react';
import { DoorMode as RmfDoorMode } from 'rmf-models/ros/rmf_door_msgs/msg';

import { StatusChip, StatusTone } from '../status-chip';
import { doorModeToString, doorTypeToString } from './door-utils';

export function doorModeToOpModeString(mode: DoorMode): string {
  switch (mode.value) {
    case RmfDoorMode.MODE_OFFLINE:
      return 'OFFLINE';
    case RmfDoorMode.MODE_UNKNOWN:
      return 'UNKNOWN';
  }
  return 'ONLINE';
}

export interface DoorTableData {
  index: number;
  doorName: string;
  levelName: string;
  doorType: number;
  doorState?: DoorState;
  onClickOpen?(): void;
  onClickClose?(): void;
}

export interface DoorDataGridTableProps {
  doors: DoorTableData[];
  onDoorClick?(ev: MuiEvent<React.MouseEvent<HTMLElement>>, doorData: DoorTableData): void;
}

export function DoorDataGridTable({ doors, onDoorClick }: DoorDataGridTableProps): JSX.Element {
  const OpModeState = (params: GridCellParams): React.ReactNode => {
    const tone: StatusTone = (() => {
      if (!params.row.doorState) {
        return 'neutral';
      }

      switch (params.row.doorState.current_mode.value) {
        case RmfDoorMode.MODE_OFFLINE:
          return 'error';
        case RmfDoorMode.MODE_UNKNOWN:
          return 'neutral';
        default:
          return 'success';
      }
    })();

    return (
      <StatusChip
        data-testid="op-mode-state"
        tone={tone}
        label={doorModeToOpModeString(params.row.doorState.current_mode)}
      />
    );
  };

  const handleEvent: GridEventListener<'rowClick'> = (
    params: GridRowParams,
    event: MuiEvent<React.MouseEvent<HTMLElement>>,
  ) => {
    if (onDoorClick) {
      onDoorClick(event, params.row);
    }
  };

  const DoorState = (params: GridCellParams): React.ReactNode => {
    const tone = React.useMemo<StatusTone>(() => {
      switch (params.row.doorState.current_mode.value) {
        case RmfDoorMode.MODE_OPEN:
          return 'success';
        case RmfDoorMode.MODE_CLOSED:
          return 'error';
        case RmfDoorMode.MODE_MOVING:
          return 'warning';
        default:
          return 'neutral';
      }
    }, [params.row.doorState.current_mode.value]);

    return (
      <StatusChip
        data-testid="door-state"
        tone={tone}
        label={
          params.row.doorState ? doorModeToString(params.row.doorState.current_mode.value) : -1
        }
      />
    );
  };

  const OpenCloseButtons = (params: GridCellParams): React.ReactNode => {
    return (
      <Box sx={{ margin: 0, padding: 0, paddingRight: 1, display: 'flex', gap: 1 }}>
        <Button
          variant="contained"
          size="small"
          aria-label="open"
          sx={{
            minWidth: 'auto',
            marginRight: 0,
          }}
          onClick={params.row.onClickOpen}
        >
          Open
        </Button>
        <Button
          variant="outlined"
          size="small"
          aria-label="close"
          sx={{
            minWidth: 'auto',
            marginRight: 0,
          }}
          onClick={params.row.onClickClose}
        >
          Close
        </Button>
      </Box>
    );
  };

  const columns: GridColDef[] = [
    {
      field: 'doorName',
      headerName: 'Name',
      width: 90,
      valueGetter: (params: GridValueGetterParams) => params.row.doorName,
      flex: 1,
      filterable: true,
    },
    {
      field: 'opMode',
      headerName: 'Op. Mode',
      width: 150,
      editable: false,
      flex: 1,
      renderCell: OpModeState,
      filterable: true,
      sortable: false,
    },
    {
      field: 'levelName',
      headerName: 'Current Floor',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) => params.row.levelName,
      flex: 1,
      filterable: true,
      sortable: false,
    },
    {
      field: 'doorType',
      headerName: 'Type',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) => doorTypeToString(params.row.doorType),
      flex: 1,
      filterable: true,
      sortable: false,
    },
    {
      field: 'doorState',
      headerName: 'Door State',
      width: 150,
      editable: false,
      flex: 1,
      renderCell: DoorState,
      filterable: true,
      sortable: false,
    },
    {
      field: '-',
      headerName: '',
      width: 150,
      editable: false,
      renderCell: OpenCloseButtons,
      flex: 1,
      filterable: false,
      sortable: false,
    },
  ];

  return (
    <DataGrid
      getRowId={(l) => l.index}
      rows={doors}
      pageSize={5}
      rowHeight={56}
      columns={columns}
      rowsPerPageOptions={[5]}
      density={'standard'}
      localeText={{
        noRowsLabel: 'No doors available.',
      }}
      onRowClick={handleEvent}
      initialState={{
        sorting: {
          sortModel: [{ field: 'doorName', sort: 'asc' }],
        },
      }}
      disableVirtualization={true}
    />
  );
}
