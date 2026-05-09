/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 通过 CSS 变量实现深/浅双主题
        bg: {
          base:    'var(--bg-base)',
          surface: 'var(--bg-surface)',
          card:    'var(--bg-card)',
          border:  'var(--bg-border)',
          hover:   'var(--bg-hover)',
        },
        brand: {
          DEFAULT: '#10a37f',
          dim:     '#0d8f6f',
          glow:    '#34d399',
        },
        accent: {
          green:  '#22d3a5',
          red:    '#f87171',
          yellow: '#fbbf24',
          blue:   '#38bdf8',
          purple: '#a78bfa',
        },
        text: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow':    'pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow':          'glow 2s ease-in-out infinite alternate',
        'slide-up':      'slideUp 0.4s ease-out',
        'fade-in':       'fadeIn 0.3s ease-out',
        'typing':        'typing 1.2s steps(3) infinite',
        'spin-slow':     'spin 3s linear infinite',
        'border-flow':   'borderFlow 3s linear infinite',
      },
      keyframes: {
        glow: {
          '0%':   { boxShadow: '0 0 8px #10a37f40' },
          '100%': { boxShadow: '0 0 20px #10a37f80, 0 0 40px #10a37f30' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        typing: {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0' },
        },
        borderFlow: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%':       { backgroundPosition: '100% 50%' },
        },
      },
      backgroundImage: {
        'gradient-radial':  'radial-gradient(var(--tw-gradient-stops))',
        'grid-pattern':     "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='0.02'%3E%3Cpath d='M0 0h40v1H0zM0 0v40h1V0z'/%3E%3C/g%3E%3C/svg%3E\")",
      },
      boxShadow: {
        'card':       '0 0 0 1px rgba(16,163,127,0.08), 0 4px 24px rgba(0,0,0,0.3)',
        'card-hover': '0 0 0 1px rgba(16,163,127,0.2), 0 8px 32px rgba(0,0,0,0.4)',
        'glow-brand': '0 0 20px rgba(16,163,127,0.35)',
        'glow-green': '0 0 12px rgba(16,163,127,0.4)',
        'inner-glow': 'inset 0 1px 0 rgba(255,255,255,0.05)',
      },
    },
  },
  plugins: [],
}
