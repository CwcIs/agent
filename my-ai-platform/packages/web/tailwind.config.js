/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts,js}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: '#0D0E12',
          surface: '#13151B',
          raised: '#191C24',
          hover: '#20242E',
        },
        text: {
          primary: '#F4F1EA',
          secondary: '#A9A29A',
          muted: '#6F767E',
        },
        brand: {
          DEFAULT: '#8B7CFF',
          soft: 'rgba(139,124,255,0.10)',
          border: 'rgba(139,124,255,0.25)',
        },
        agent: {
          knowledge: '#6EA8FF',
          review: '#FFB86C',
          brain: '#B892FF',
        },
        success: '#70E0A3',
        warning: '#FFD166',
        danger: '#FF6B6B',
      },
      borderRadius: {
        card: '14px',
        panel: '18px',
        composer: '22px',
      },
      maxWidth: {
        content: '720px',
      },
      fontSize: {
        'page': ['20px', '28px'],
        'thread': ['18px', '26px'],
      },
      transitionTimingFunction: {
        drawer: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
