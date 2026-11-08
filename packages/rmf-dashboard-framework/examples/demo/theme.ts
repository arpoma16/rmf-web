import { alpha, createTheme } from '@mui/material';

import { DESIGN_THEMES, DesignThemeName, DesignTokens, getDesignThemeName } from './design-tokens';

const FONT_FAMILY = 'Inter, system-ui, sans-serif';
// Radio de las esquinas de las tarjetas (Robots, Doors, Map) y del plano del mapa.
const CARD_RADIUS = 4;

export const createLynceTheme = (name: DesignThemeName = getDesignThemeName()) => {
  const t: DesignTokens = DESIGN_THEMES[name];

  return createTheme({
    palette: {
      mode: t.dark ? 'dark' : 'light',
      primary: { main: t.accent, light: t.accentLine, contrastText: t.accentText },
      // NEW TASK usa el color secundario
      secondary: { main: t.accent, contrastText: t.accentText },
      // tinta de iconos y textos secundarios de acento
      info: { main: t.accentInk },
      // chips de estado: main = texto, light = fondo
      success: { main: t.okFg, light: t.okBg },
      error: { main: t.clFg, light: t.clBg },
      warning: { main: t.idleFg, light: t.idleBg },
      background: { default: t.bg, paper: t.surface },
      text: { primary: t.text, secondary: t.muted },
      divider: t.border,
      mapBackground: t.mapBg,
    },
    shape: { borderRadius: CARD_RADIUS },
    typography: { fontFamily: FONT_FAMILY },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: { backgroundColor: t.bg, color: t.text },
          '.MuiDataGrid-root': {
            fontVariantNumeric: 'tabular-nums',
            border: 'none',
          },
          '.MuiDataGrid-columnHeaders': {
            color: t.muted,
            borderBottom: `1px solid ${t.border}`,
          },
          '.MuiDataGrid-columnHeaderTitle': { fontSize: 12, fontWeight: 600 },
          '.MuiDataGrid-cell': {
            fontSize: 14,
            padding: '0 12px',
            borderBottom: `1px solid ${t.border}`,
          },
          '.MuiDataGrid-cell[data-field="name"], .MuiDataGrid-cell[data-field="doorName"]': {
            fontWeight: 600,
          },
          '.MuiDataGrid-footerContainer': { color: t.muted, borderTop: `1px solid ${t.border}` },
          '.MuiTablePagination-root': { color: t.muted },
          '.MuiTablePagination-actions .Mui-disabled': { opacity: 0.45 },
        },
      },
      MuiAppBar: {
        variants: [
          // Barra principal (`sticky`)
          {
            props: { position: 'sticky' },
            style: {
              backgroundColor: t.appbar,
              backgroundImage: 'none',
              color: t.appbarText,
              minHeight: 64,
              '& .app-brand-title': { fontSize: 17, fontWeight: 700, color: t.appbarText },
              '& .app-brand-subtitle': { fontSize: 12, color: t.tabMuted },
              '& .MuiDivider-root': { borderColor: alpha(t.tabMuted, 0.3) },
              '& .MuiTabs-indicator': { height: 3, backgroundColor: t.tabLine },
              '& .MuiTab-root': {
                color: t.tabMuted,
                opacity: 1,
                '&.Mui-selected': { color: t.appbarText },
                '& .MuiTypography-root': {
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                },
              },
              '& .MuiIconButton-root': { color: t.appbarText, minWidth: 44, minHeight: 44 },
            },
          },
          // Cabeceras de las tarjetas (Robots, Doors, Map, ...): `static`
          {
            props: { position: 'static' },
            style: {
              backgroundColor: t.head,
              backgroundImage: 'none',
              color: t.title,
              boxShadow: 'none',
              borderBottom: `1px solid ${t.border}`,
              '& .MuiTypography-h6': { fontSize: 16, fontWeight: 700, color: t.title },
              '& .MuiIconButton-root': { color: t.muted },
            },
          },
        ],
      },
      MuiPaper: {
        styleOverrides: {
          outlined: {
            border: `1px solid ${t.border}`,
            borderRadius: CARD_RADIUS,
            boxShadow: t.shadow,
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: { borderRadius: 8, minHeight: 44, fontWeight: 700 },
          sizeSmall: { fontSize: 12 },
          outlinedPrimary: {
            color: t.accentInk,
            borderColor: t.accentLine,
            backgroundColor: 'transparent',
            '&:hover': { borderColor: t.accentLine, backgroundColor: alpha(t.accent, 0.08) },
          },
        },
      },
      MuiBadge: {
        styleOverrides: {
          // campana de notificaciones
          colorSecondary: { backgroundColor: t.warm, color: t.warmText },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            '&.MuiInputBase-sizeSmall': { minHeight: 44 },
            '& .MuiOutlinedInput-notchedOutline': { borderColor: t.border },
          },
        },
      },
    },
  });
};

export const lynceTheme = createLynceTheme();
