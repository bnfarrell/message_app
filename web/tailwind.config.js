const tokens = [
  'bg', 'bg2', 'nav', 'surface', 'surface2', 'border', 'border2', 'border3',
  'text', 'text2', 'text3', 'text4', 'accent', 'accentText', 'roomNum', 'sel',
  'outBg', 'outText', 'autoBg', 'autoText', 'autoBorder',
  'noteBg', 'noteBorder', 'noteText', 'noteIcon',
  'okBg', 'okText', 'okBorder', 'okBtn', 'okBtnText', 'okBanner',
  'warnBg', 'warnText', 'dangerBg', 'dangerText', 'danger',
  'presenceBg', 'presenceText', 'presenceAv',
  'avMuted', 'avText', 'tagBg', 'tagText', 'timerDoneBg', 'timerDoneText',
]

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: Object.fromEntries(tokens.map((t) => [t, `var(--${t})`])),
      fontFamily: {
        ui: ['"Space Grotesk"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      borderRadius: { DEFAULT: '8px', card: '10px' },
    },
  },
  plugins: [],
}
