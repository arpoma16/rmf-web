import {
  DataGrid,
  GridCellParams,
  GridColDef,
  GridEventListener,
  GridRowParams,
  GridValueGetterParams,
  MuiEvent,
} from '@mui/x-data-grid';
import { ApiServerModelsRmfApiRobotStateStatus as Status, Commission } from 'api-client';
import * as React from 'react';

import { StatusChip, StatusTone } from '../status-chip';
import { robotStatusToUpperCase } from './utils';

export interface RobotTableData {
  fleet: string;
  name: string;
  status?: Status;
  battery?: number;
  estFinishTime?: number;
  lastUpdateTime?: number;
  level?: string;
  commission?: Commission;
}

export interface RobotDataGridTableProps {
  onRobotClick?(ev: MuiEvent<React.MouseEvent<HTMLElement>>, robotName: RobotTableData): void;
  robots: RobotTableData[];
}

export function RobotDataGridTable({ onRobotClick, robots }: RobotDataGridTableProps): JSX.Element {
  const handleEvent: GridEventListener<'rowClick'> = (
    params: GridRowParams,
    event: MuiEvent<React.MouseEvent<HTMLElement>>,
  ) => {
    if (onRobotClick) {
      onRobotClick(event, params.row);
    }
  };

  const StatusCell = (params: GridCellParams): React.ReactNode => {
    const robotDecommissioned =
      params.row.commission && params.row.commission.dispatch_tasks === false;

    const tone: StatusTone = (() => {
      if (robotDecommissioned) {
        return 'neutral';
      }

      switch (params.row.status) {
        case Status.Error:
          return 'error';
        case Status.Offline:
        case Status.Uninitialized:
          return 'neutral';
        case Status.Working:
          return 'success';
        default:
          // idle, charging and any other state
          return 'warning';
      }
    })();

    return (
      <StatusChip
        data-testid="status"
        tone={tone}
        label={robotDecommissioned ? 'DECOMMISSIONED' : robotStatusToUpperCase(params.row.status)}
      />
    );
  };

  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: 'Name',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) => params.row.name,
      flex: 1,
      filterable: true,
    },
    {
      field: 'fleet',
      headerName: 'Fleet',
      width: 90,
      valueGetter: (params: GridValueGetterParams) => params.row.fleet,
      flex: 1,
      filterable: true,
    },
    {
      field: 'estFinishTime',
      headerName: 'Est. Task Finish Time',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) =>
        params.row.estFinishTime ? new Date(params.row.estFinishTime).toLocaleString() : '-',
      flex: 1,
      filterable: true,
    },
    {
      field: 'level',
      headerName: 'Level',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) => params.row.level,
      flex: 1,
      filterable: true,
    },
    {
      field: 'battery',
      headerName: 'Battery',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) => `${(params.row.battery * 100).toFixed(2)}%`,
      flex: 1,
      filterable: true,
    },
    {
      field: 'lastUpdateTime',
      headerName: 'Last Updated',
      width: 150,
      editable: false,
      valueGetter: (params: GridValueGetterParams) =>
        params.row.lastUpdateTime ? new Date(params.row.lastUpdateTime).toLocaleString() : '-',
      flex: 1,
      filterable: true,
    },
    {
      field: 'status',
      headerName: 'Status',
      editable: false,
      flex: 1,
      renderCell: StatusCell,
      filterable: true,
    },
  ];

  return (
    <DataGrid
      getRowId={(r) => r.name}
      rows={robots}
      pageSize={5}
      rowHeight={48}
      columns={columns}
      rowsPerPageOptions={[5]}
      density={'standard'}
      onRowClick={handleEvent}
      initialState={{
        sorting: {
          sortModel: [{ field: 'name', sort: 'asc' }],
        },
      }}
      disableVirtualization={true}
    />
  );
}
