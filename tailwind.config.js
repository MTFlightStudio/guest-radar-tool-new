/** @type {import('tailwindcss').Config} */
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      textShadow: {
        'default': '0 1px 3px rgba(0, 0, 0, 0.7)',
      },
    },
  },
  plugins: [
    function ({ addUtilities }) {
      const newUtilities = {
        '.shadow-text': {
          textShadow: '0 1px 3px rgba(0, 0, 0, 0.7)',
        },
      }
      addUtilities(newUtilities)
    }
  ]
}
