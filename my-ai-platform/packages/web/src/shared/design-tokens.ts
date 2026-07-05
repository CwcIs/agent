/**
 * AI Thought Studio design tokens.
 * Single source of truth for colors, spacing, radii, and agent metadata.
 */

export const colors = {
  appBg: '#0D0E12',
  surfaceBase: '#13151B',
  surfaceRaised: '#191C24',
  surfaceHover: '#20242E',
  borderSubtle: 'rgba(255,255,255,0.06)',
  borderStrong: 'rgba(255,255,255,0.10)',
  textPrimary: '#F4F1EA',
  textSecondary: '#A9A29A',
  textTertiary: '#6F767E',
  brand: '#8B7CFF',
  brandSoft: 'rgba(139,124,255,0.10)',
  brandBorder: 'rgba(139,124,255,0.25)',
  success: '#70E0A3',
  warning: '#FFD166',
  danger: '#FF6B6B',
} as const;

export const agentColors: Record<string, { hex: string; bg: string; border: string }> = {
  knowledge: { hex: '#6EA8FF', bg: 'rgba(110,168,255,0.06)', border: 'rgba(110,168,255,0.18)' },
  review: { hex: '#FFB86C', bg: 'rgba(255,184,108,0.06)', border: 'rgba(255,184,108,0.18)' },
  brain: { hex: '#B892FF', bg: 'rgba(184,146,255,0.06)', border: 'rgba(184,146,255,0.18)' },
};

export const agentMeta: Record<string, { label: string; short: string; verb: string; role: string }> = {
  knowledge: { label: 'Knowledge', short: 'K', verb: 'Reading memory', role: '检索并整理相关记忆' },
  review: { label: 'Review', short: 'R', verb: 'Checking assumptions', role: '挑战隐含假设与盲点' },
  brain: { label: 'Brain', short: 'B', verb: 'Exploring ideas', role: '联想扩展相邻可能性' },
};

export const TAG_AGENT_MAP: Record<string, string> = {
  review: 'review',
  critique: 'review',
  brain: 'brain',
};

export const typography = {
  pageTitle: { size: '20px', lineHeight: '28px', weight: '600' },
  threadTitle: { size: '18px', lineHeight: '26px', weight: '600' },
  body: { size: '15px', lineHeight: '24px', weight: '400' },
  small: { size: '13px', lineHeight: '20px', weight: '400' },
  micro: { size: '11px', lineHeight: '14px', weight: '500' },
} as const;

export const radii = {
  sm: '6px',
  md: '10px',
  card: '14px',
  panel: '18px',
  composer: '22px',
} as const;

export const layout = {
  leftRailWidth: '248px',
  drawerWidth: '420px',
  maxContentWidth: '760px',
} as const;

export const shadows = {
  panel: '0 12px 40px rgba(0,0,0,0.28), 0 1px 0 rgba(255,255,255,0.04) inset',
  card: '0 2px 8px rgba(0,0,0,0.20)',
} as const;

export const easing = {
  drawer: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  hover: 'cubic-bezier(0.3, 0, 0.5, 1)',
} as const;

export const durations = {
  drawer: 180,
  hover: 150,
  toast: 200,
} as const;
