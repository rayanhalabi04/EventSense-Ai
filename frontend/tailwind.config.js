/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        display: ['Newsreader', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Core brand
        primary: {
          DEFAULT: '#172033',
          soft: '#25314A',
          container: '#172033',
        },
        secondary: {
          DEFAULT: '#A58F7A',
          container: '#F8DEC6',
        },
        accent: {
          DEFAULT: '#C8A96A',
          soft: '#F3E8D2',
        },
        // Backgrounds
        bg: {
          warm: '#FBF7EF',
          clean: '#FFFDF8',
          ivory: '#FBF7EF',
        },
        surface: {
          DEFAULT: '#FFFFFF',
          warm: '#F8F1E7',
          dim: '#E1D9D0',
          low: '#FBF2E9',
          container: '#F5ECE4',
          high: '#EFE7DE',
          highest: '#EAE1D8',
        },
        // Neutrals
        ink: {
          950: '#151515',
          900: '#242424',
          700: '#4B4B4B',
          500: '#77716A',
          300: '#D8D0C6',
          200: '#EAE3DA',
          100: '#F5EFE6',
          50: '#FCFAF6',
        },
        // Semantic
        success: {
          DEFAULT: '#2F7D5B',
          soft: '#E4F3EC',
        },
        warning: {
          DEFAULT: '#B7791F',
          soft: '#FFF4D8',
        },
        danger: {
          DEFAULT: '#A33A3A',
          soft: '#FBE6E6',
        },
        info: {
          DEFAULT: '#3B6F8F',
          soft: '#E6F1F6',
        },
        // Text
        text: {
          primary: '#172033',
          body: '#3D3A36',
          muted: '#77716A',
          inverse: '#FFFDF8',
          accent: '#8C6B2F',
        },
        // Borders
        border: {
          DEFAULT: '#E3DACE',
          strong: '#CFC3B5',
          focus: '#C8A96A',
          danger: '#D99A9A',
        },
      },
      borderRadius: {
        sm: '8px',
        DEFAULT: '12px',
        md: '12px',
        lg: '16px',
        xl: '20px',
      },
      boxShadow: {
        card: '0 8px 24px rgba(23, 32, 51, 0.06)',
        'card-hover': '0 12px 32px rgba(23, 32, 51, 0.10)',
        modal: '0 24px 64px rgba(23, 32, 51, 0.14)',
        sm: '0 2px 8px rgba(23, 32, 51, 0.06)',
        nav: '0 1px 0 #E3DACE',
      },
      spacing: {
        18: '4.5rem',
        22: '5.5rem',
      },
    },
  },
  plugins: [],
}
