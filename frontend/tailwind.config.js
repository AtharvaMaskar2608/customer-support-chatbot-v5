/**
 * Build (from frontend/):
 *   npx tailwindcss@3 -c tailwind.config.js -o css/tailwind.css --minify
 * Scans index.html AND js/app.js — several utility classes only exist in the
 * JS render-function template strings.
 * @type {import('tailwindcss').Config}
 */
module.exports = {
  content: ['./index.html', './js/app.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Bricolage Grotesque"', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink: { DEFAULT: '#eef1fb', dim: '#a6aecd', mute: '#6a739a' },
        brand: {
          50: '#eef3ff', 100: '#dde7ff', 200: '#c2d4ff', 300: '#9cb8ff',
          400: '#7396ff', 500: '#4f7cff', 600: '#3a5ef7', 700: '#2f49d1',
          800: '#2b3ca3', 900: '#283879',
        },
      },
      boxShadow: {
        glow: '0 0 32px -6px rgba(79, 124, 255, 0.45)',
        lift: '0 16px 40px -12px rgba(79, 124, 255, 0.5)',
        glass: '0 24px 48px -20px rgba(2, 4, 18, 0.7)',
      },
    },
  },
};
