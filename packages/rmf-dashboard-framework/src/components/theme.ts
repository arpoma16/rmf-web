import { ThemeProvider } from '@mui/material';

declare module '@mui/material/styles' {
  interface Palette {
    /** Background of the panel surrounding the map plan. Falls back to the default background. */
    mapBackground?: string;
  }
  interface PaletteOptions {
    mapBackground?: string;
  }
}

export type MuiTheme = React.ComponentProps<typeof ThemeProvider>['theme'];

export interface DashboardThemes {
  default: MuiTheme;
  dark?: MuiTheme;
}
