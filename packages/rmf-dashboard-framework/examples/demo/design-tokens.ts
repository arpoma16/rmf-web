// Tokens del sistema de diseño de Flota LINCE. Ver DESIGN.md en la raíz del repo.
// Para cambiar de tema: `VITE_DESIGN_THEME=B` (o `C`) en el entorno de Vite, o cambiar
// `DEFAULT_DESIGN_THEME`.

export interface DesignTokens {
  dark: boolean;
  bg: string;
  surface: string;
  head: string;
  border: string;
  text: string;
  muted: string;
  title: string;
  appbar: string;
  appbarText: string;
  tabMuted: string;
  tabLine: string;
  accent: string;
  accentText: string;
  accentInk: string;
  accentLine: string;
  warm: string;
  warmText: string;
  idleBg: string;
  idleFg: string;
  okBg: string;
  okFg: string;
  clBg: string;
  clFg: string;
  mapBg: string;
  shadow: string;
}

const SOFT_SHADOW = '0 1px 2px rgba(16, 24, 28, 0.06), 0 1px 3px rgba(16, 24, 28, 0.04)';

export const DESIGN_THEMES = {
  /** A · Verde petróleo */
  A: {
    dark: false,
    bg: '#EDF1F2',
    surface: '#FFFFFF',
    head: '#F4F8F8',
    border: '#DAE3E5',
    text: '#1B2B30',
    muted: '#566B71',
    title: '#0B5A62',
    appbar: '#11252B',
    appbarText: '#EAF3F4',
    tabMuted: '#9DB6BA',
    tabLine: '#3CC9C0',
    accent: '#0E7C86',
    accentText: '#FFFFFF',
    accentInk: '#0B6169',
    accentLine: '#7FB5BA',
    warm: '#FFB020',
    warmText: '#1F1500',
    idleBg: '#FFF0D6',
    idleFg: '#8A4B00',
    okBg: '#DDF3E4',
    okFg: '#14663A',
    clBg: '#FDE4E1',
    clFg: '#A02A22',
    mapBg: '#E4ECEE',
    shadow: SOFT_SHADOW,
  },
  /** B · Azul corporativo */
  B: {
    dark: false,
    bg: '#EEF2F8',
    surface: '#FFFFFF',
    head: '#F4F7FC',
    border: '#D8E0EE',
    text: '#17233A',
    muted: '#55647F',
    title: '#1E3A8A',
    appbar: '#0F2747',
    appbarText: '#EAF0FA',
    tabMuted: '#A9BCD9',
    tabLine: '#5AA9FF',
    accent: '#1D4ED8',
    accentText: '#FFFFFF',
    accentInk: '#1D4ED8',
    accentLine: '#93ADEB',
    warm: '#FFB020',
    warmText: '#1F1500',
    idleBg: '#FFF0D6',
    idleFg: '#8A4B00',
    okBg: '#DDF3E4',
    okFg: '#14663A',
    clBg: '#FDE4E1',
    clFg: '#A02A22',
    mapBg: '#E3E9F3',
    shadow: SOFT_SHADOW,
  },
  /** C · Grafito oscuro */
  C: {
    dark: true,
    bg: '#0F1418',
    surface: '#171E24',
    head: '#1C252C',
    border: '#2A353E',
    text: '#E6EDF2',
    muted: '#93A4B1',
    title: '#FFD08A',
    appbar: '#0A0E11',
    appbarText: '#E6EDF2',
    tabMuted: '#8FA1AE',
    tabLine: '#F5A524',
    accent: '#F5A524',
    accentText: '#1A1200',
    accentInk: '#F5B84A',
    accentLine: '#6B5321',
    warm: '#F5A524',
    warmText: '#1A1200',
    idleBg: '#3A2E12',
    idleFg: '#FFC969',
    okBg: '#12331F',
    okFg: '#6FDB9B',
    clBg: '#3B1B1A',
    clFg: '#FF9A92',
    mapBg: '#11171B',
    shadow: 'none',
  },
} satisfies Record<string, DesignTokens>;

export type DesignThemeName = keyof typeof DESIGN_THEMES;

export const DEFAULT_DESIGN_THEME: DesignThemeName = 'A';

export const getDesignThemeName = (): DesignThemeName => {
  const name = import.meta.env.VITE_DESIGN_THEME as string | undefined;
  return name && name in DESIGN_THEMES ? (name as DesignThemeName) : DEFAULT_DESIGN_THEME;
};
