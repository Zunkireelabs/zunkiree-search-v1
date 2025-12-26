// Design Tokens for Zunkiree Search Widget v2
// See docs/widget-style-guide.md for full documentation

export const colors = {
  // Primary (defaults - overridden by config)
  primary: {
    DEFAULT: '#2563EB',
    hover: '#1D4ED8',
    light: 'rgba(37, 99, 235, 0.1)',
    text: '#FFFFFF',
  },

  // Neutrals
  background: '#FFFFFF',
  surface: '#F9FAFB',
  surfaceHover: '#F3F4F6',

  // Borders
  border: {
    DEFAULT: '#E5E7EB',
    focus: '#2563EB',
    hover: '#D1D5DB',
  },

  // Text
  text: {
    primary: '#111827',
    secondary: '#6B7280',
    muted: '#9CA3AF',
    inverse: '#FFFFFF',
  },

  // Semantic
  success: '#10B981',
  error: '#EF4444',
  warning: '#F59E0B',
};

export const typography = {
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",

  fontSize: {
    xs: '12px',
    sm: '13px',
    base: '15px',
    lg: '16px',
    xl: '18px',
    '2xl': '24px',
  },

  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
  },

  lineHeight: {
    tight: '1.25',
    normal: '1.5',
    relaxed: '1.625',
  },
};

export const spacing = {
  0: '0',
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  8: '32px',
  10: '40px',
  12: '48px',

  container: {
    padding: '24px',
    paddingMobile: '16px',
  },

  searchBar: {
    paddingX: '16px',
    paddingY: '14px',
    height: {
      hero: '56px',
      inline: '48px',
      floating: '44px',
    },
  },

  resultCard: {
    padding: '20px',
    gap: '16px',
  },

  chip: {
    paddingX: '12px',
    paddingY: '6px',
    gap: '8px',
  },
};

export const borderRadius = {
  none: '0',
  sm: '4px',
  DEFAULT: '6px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '9999px',

  searchBar: {
    rounded: '12px',
    pill: '9999px',
  },
  resultCard: '8px',
  chip: '6px',
};

export const shadows = {
  none: 'none',
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  DEFAULT: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)',

  searchBar: {
    default: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
    focus: '0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06)',
    hover: '0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.04)',
  },
  resultsPanel: '0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.05)',
};

export const transitions = {
  duration: {
    fast: '100ms',
    DEFAULT: '150ms',
    slow: '200ms',
    slower: '300ms',
  },
  timing: {
    DEFAULT: 'ease-in-out',
    in: 'ease-in',
    out: 'ease-out',
  },
  default: '150ms ease-in-out',
  fast: '100ms ease-in-out',
  slow: '200ms ease-out',
};

export const zIndex = {
  base: '1',
  dropdown: '1000',
  widget: '9999',
  resultsPanel: '10000',
};

// Helper to generate CSS custom properties
export const generateCSSVariables = (primaryColor: string): string => {
  // Calculate hover color (10% darker)
  const darkenColor = (hex: string, percent: number): string => {
    const num = parseInt(hex.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.max(0, (num >> 16) - amt);
    const G = Math.max(0, ((num >> 8) & 0x00ff) - amt);
    const B = Math.max(0, (num & 0x0000ff) - amt);
    return `#${(0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1)}`;
  };

  // Calculate light color (10% opacity)
  const hexToRgba = (hex: string, alpha: number): string => {
    const num = parseInt(hex.replace('#', ''), 16);
    const R = num >> 16;
    const G = (num >> 8) & 0x00ff;
    const B = num & 0x0000ff;
    return `rgba(${R}, ${G}, ${B}, ${alpha})`;
  };

  return `
    --zk-primary: ${primaryColor};
    --zk-primary-hover: ${darkenColor(primaryColor, 10)};
    --zk-primary-light: ${hexToRgba(primaryColor, 0.1)};
  `;
};
