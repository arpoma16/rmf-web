import { Tab } from '@mui/material';
import { waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';

import { AuthenticatorProvider, RmfApiProvider } from '../hooks';
import { RmfApi, StubAuthenticator } from '../services';
import { MockRmfApi, render, TestProviders } from '../utils/test-utils.test';
import AppBar from './appbar';

describe('AppBar', () => {
  const Base = (props: React.PropsWithChildren<{}>) => {
    const rmfApi = React.useMemo<RmfApi>(() => {
      const mockRmfApi = new MockRmfApi();
      // mock out some api calls so they never resolves
      mockRmfApi.tasksApi.getFavoritesTasksFavoriteTasksGet = () => new Promise(() => {});
      mockRmfApi.alertsApi.getUnrespondedAlertsAlertsUnrespondedRequestsGet = () =>
        new Promise(() => {});
      mockRmfApi.buildingApi.getPreviousFireAlarmTriggerBuildingMapPreviousFireAlarmTriggerGet =
        () => new Promise(() => {});
      return mockRmfApi;
    }, []);
    return (
      <TestProviders>
        <RmfApiProvider value={rmfApi}>{props.children}</RmfApiProvider>
      </TestProviders>
    );
  };

  it('renders with navigation bar', () => {
    const root = render(
      <Base>
        <AppBar
          tabs={[<Tab key="test" label="test" value="test" />]}
          tabValue="test"
          helpLink=""
          reportIssueLink=""
        />
      </Base>,
    );
    expect(root.getAllByRole('tablist').length > 0).toBeTruthy();
  });

  it('shows the configured title and subtitle instead of the upstream branding', () => {
    const root = render(
      <Base>
        <AppBar
          tabs={[<Tab key="test" label="test" value="test" />]}
          tabValue="test"
          helpLink=""
          reportIssueLink=""
        />
      </Base>,
    );
    expect(root.getByText('Flota LINCE')).toBeTruthy();
    expect(root.getByText('Monitorización de robots · Indra')).toBeTruthy();
    expect(root.queryByText(/Open-RMF/)).toBeNull();
  });

  it('has no help or report issues buttons and the title comes before the tabs', () => {
    const root = render(
      <Base>
        <AppBar
          tabs={[<Tab key="test" label="test" value="test" />]}
          tabValue="test"
          helpLink="https://example.com/help"
          reportIssueLink="https://example.com/issues"
        />
      </Base>,
    );
    expect(root.queryByLabelText('help')).toBeNull();
    expect(root.queryByLabelText('warning')).toBeNull();
    const title = root.getByText('Flota LINCE');
    const tabs = root.getByRole('tablist');
    expect(title.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('user button is shown when there is an authenticated user', () => {
    const root = render(
      <Base>
        <AppBar
          tabs={[<Tab key="test" label="test" value="test" />]}
          tabValue="test"
          helpLink=""
          reportIssueLink=""
        />
      </Base>,
    );
    expect(root.getByLabelText('user-btn')).toBeTruthy();
  });

  it('logout is triggered when logout button is clicked', async () => {
    const authenticator = new StubAuthenticator();
    const spy = vi.spyOn(authenticator, 'logout').mockImplementation(() => undefined as any);
    const root = render(
      <Base>
        <AuthenticatorProvider value={authenticator}>
          <AppBar
            tabs={[<Tab key="test" label="test" value="test" />]}
            tabValue="test"
            helpLink=""
            reportIssueLink=""
          />
        </AuthenticatorProvider>
      </Base>,
    );
    userEvent.click(root.getByLabelText('user-btn'));
    await expect(waitFor(() => root.getByText('Logout'))).resolves.not.toThrow();
    userEvent.click(root.getByText('Logout'));
    await expect(waitFor(() => expect(spy).toHaveBeenCalledTimes(1))).resolves.not.toThrow();
  });

  it('does not render the upstream logo in the navigation bar', () => {
    const root = render(
      <Base>
        <AppBar
          tabs={[<Tab key="test" label="test" value="test" />]}
          tabValue="test"
          helpLink=""
          reportIssueLink=""
        />
      </Base>,
    );
    expect(root.container.querySelector('img')).toBeNull();
  });
});
