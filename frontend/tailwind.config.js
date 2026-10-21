/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        stadium: {
          950: '#020617', // Dark stadium athletic background
          900: '#0f172a', // Elevated surface
          800: '#1e293b', // Card background / borders
          700: '#334155', // Borders / dividers
          600: '#475569',
          500: '#64748b', // Subtle text / icons
          400: '#94a3b8', // Muted text
          300: '#cbd5e1',
          200: '#e2e8f0',
          100: '#f1f5f9',
          50: '#f8fafc',  // Primary light text
        },
        turf: {
          DEFAULT: '#10b981', // emerald-500
          light: '#34d399',   // emerald-400
          dark: '#059669',    // emerald-600
        },
        trophy: {
          DEFAULT: '#f59e0b', // amber-500
          light: '#fbbf24',   // amber-400
          dark: '#d97706',    // amber-600
        },
        alert: {
          DEFAULT: '#f43f5e', // rose-500
          light: '#fb7185',   // rose-400
          dark: '#e11d48',    // rose-600
        },
      },
      spacing: {
        'safe-top': 'env(safe-area-inset-top)',
        'safe-bottom': 'env(safe-area-inset-bottom)',
        'safe-left': 'env(safe-area-inset-left)',
        'safe-right': 'env(safe-area-inset-right)',
      },
      minHeight: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      minWidth: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
};
