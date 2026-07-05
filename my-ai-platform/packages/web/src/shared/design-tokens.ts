/**
 * AI Thought Studio — Design Tokens
 *
 * 单一数据源：所有颜色、字体、圆角、间距、Agent 元数据从这里引用。
 * 组件中不再硬编码 hex 值。
 */

// ── Color Palette (Warm Dark) ──
export const colors = {
  appBg:        '#0D0E12',
  surfaceBase:  '#13151B',
  surfaceRaised: '#191C24',
  surfaceHover: '#20242E',
  borderSubtle:  'rgba(255,255,255,0.06)',
  borderStrong:  'rgba(255,255,255,0.10)',
  textPrimary:   '#F4F1EA',
  textSecondary: '#A9A29A',
  textTertiary:  '#6F767E',
  brand:         '#8B7CFF',
  brandSoft:     'rgba(139,124,255,0.10)',
  brandBorder:   'rgba(139,124,255,0.25)',
  success:       '#70E0A3',
  warning:       '#FFD166',
  danger:        '#FF6B6B',
} as const;

// ── Agent Colors ──
export const agentColors: Record<string, { hex: string; bg: string; border: string }> = {
  knowledge: { hex: '#6EA8FF', bg: 'rgba(110,168,255,0.06)', border: 'rgba(110,168,255,0.18)' },
  review:    { hex: '#FFB86C', bg: 'rgba(255,184,108,0.06)', border: 'rgba(255,184,108,0.18)' },
  brain:     { hex: '#B892FF', bg: 'rgba(184,146,255,0.06)', border: 'rgba(184,146,255,0.18)' },
};

// ── Agent Metadata ──
export const agentMeta: Record<string, { label: string; short: string; verb: string; role: string }> = {
  knowledge: { label: 'Knowledge', short: 'K', verb: '正在检索', role: '检索相关记忆…' },
  review:    { label: 'Review',    short: 'R', verb: '正在挑战', role: '检查隐含假设…' },
  brain:     { label: 'Brain',     short: 'B', verb: '正在联想', role: '跨界联想扩展…' },
};

// ── Agent Tag Mapping (hashtag → agent_id) ──
export const TAG_AGENT_MAP: Record<string, string> = {
  review: 'review',
  critique: 'review',
  brain: 'brain',
};

// ── Typography ──
export const typography = {
  pageTitle:   { size: '20px', lineHeight: '28px', weight: '600' },
  threadTitle: { size: '18px', lineHeight: '26px', weight: '600' },
  body:        { size: '15px', lineHeight: '24px', weight: '400' },
  small:       { size: '13px', lineHeight: '20px', weight: '400' },
  micro:       { size: '11px', lineHeight: '14px', weight: '500' },
} as const;

// ── Border Radii ──
export const radii = {
  sm:       '6px',
  md:       '10px',
  card:     '14px',
  panel:    '18px',
  composer: '22px',
} as const;

// ── Layout ──
export const layout = {
  leftRailWidth:  '248px',
  drawerWidth:    '420px',
  maxContentWidth: '720px',
} as const;

// ── Shadows ──
export const shadows = {
  panel: '0 12px 40px rgba(0,0,0,0.28), 0 1px 0 rgba(255,255,255,0.04) inset',
  card:  '0 2px 8px rgba(0,0,0,0.20)',
} as const;

// ── Animation ──
export const easing = {
  drawer: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  hover:  'cubic-bezier(0.3, 0, 0.5, 1)',
} as const;

export const durations = {
  drawer: 180,
  hover:  150,
  toast:  200,
} as const;
