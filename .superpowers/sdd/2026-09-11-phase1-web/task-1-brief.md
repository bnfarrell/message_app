### Task 1: Scaffold, design tokens and Tailwind

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/tailwind.config.js`, `web/postcss.config.js`, `web/index.html`, `web/.gitignore`, `web/vitest.setup.ts`
- Create: `web/src/index.css`, `web/src/lib/cn.ts`, `web/src/main.tsx`, `web/src/App.tsx`
- Test: `web/src/index.css.test.ts`, `web/src/lib/cn.test.ts`
- Modify: `package.json` (repo root — add `web`, `dev`, `gen:types` next to the existing `server`, `seed`, `test:server`, `schema`)

**Interfaces:**
- Consumes: nothing.
- Produces: `cn(...parts: (string | false | null | undefined)[]): string`; the 45 CSS custom properties listed below on `:root` and `[data-theme="light"]`; Tailwind colour names identical to the token names (`bg`, `bg2`, `nav`, `surface`, `surface2`, `border`, `border2`, `border3`, `text`, `text2`, `text3`, `text4`, `accent`, `accentText`, `roomNum`, `sel`, `outBg`, `outText`, `autoBg`, `autoText`, `autoBorder`, `noteBg`, `noteBorder`, `noteText`, `noteIcon`, `okBg`, `okText`, `okBorder`, `okBtn`, `okBtnText`, `okBanner`, `warnBg`, `warnText`, `dangerBg`, `dangerText`, `danger`, `presenceBg`, `presenceText`, `presenceAv`, `avMuted`, `avText`, `tagBg`, `tagText`, `timerDoneBg`, `timerDoneText`) so `bg-surface2` / `text-text3` / `border-border2` work; font families `font-ui` and `font-mono`.

Every later task styles with these names. **Do not invent a colour** — if a mockup shows a colour, it is one of these 45.

- [ ] **Step 1: Write `web/package.json`**

```json
{
  "name": "concierge-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "gen:types": "json2ts --input src/api/schema.json --output src/api/types.generated.ts --style.singleQuote --no-additionalProperties --unreachableDefinitions",
    "lint": "eslint src --ext .ts,.tsx"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.56.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@playwright/test": "^1.47.2",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.8",
    "@types/react-dom": "^18.3.0",
    "@typescript-eslint/eslint-plugin": "^8.7.0",
    "@typescript-eslint/parser": "^8.7.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "eslint": "^8.57.1",
    "eslint-plugin-react-hooks": "^4.6.2",
    "jsdom": "^25.0.1",
    "json-schema-to-typescript": "^15.0.2",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: Write the config files**

`web/vite.config.ts` — the proxy targets the Flask dev server on 5000. `/ws` needs `ws: true` or the upgrade never happens. `/a` is proxied so asset short links resolve in dev.

Two things here are load-bearing and easy to get wrong:

- **`defineConfig` comes from `vitest/config`, not `vite`.** This file carries a `test:` key, which
  Vite's own `defineConfig` does not type — `tsc -b` rejects it and Step 10's build fails.
  `vitest/config` re-exports every Vite option, so nothing else changes.
- **`test.include` is scoped to `src/`.** Vitest's default include would also match Task 21's
  Playwright specs under `web/tests/e2e/`, and Vitest cannot run those — it would fail on the
  `@playwright/test` import. Scoping it now avoids a breakage that surfaces at Task 21 disguised as
  a Playwright problem.

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const API = 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/a': { target: API, changeOrigin: true },
      '/ws': { target: API, ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    // Unit and component tests only. tests/e2e/ belongs to Playwright.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vitest.setup.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "composite": true,
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts", "playwright.config.ts"]
}
```

`web/postcss.config.js`:

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

`web/.gitignore`:

```
node_modules/
dist/
playwright-report/
test-results/
.env
.env.local
```

- [ ] **Step 3: Write `web/tailwind.config.js`**

Each colour resolves through `var()` so one `data-theme` swap repaints the app. No `theme.extend.colors` entry may hold a literal hex.

```js
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
```

- [ ] **Step 4: Write `web/src/index.css` with both palettes verbatim**

These are the exact values from `docs/mockups/Main.dc.html` (dark) and `MainLight.dc.html` (light). Copy them character for character; they are the approved design.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: #0e1116; --bg2: #11151b; --nav: #0b0e12; --surface: #161a21;
  --surface2: #1a1f28; --border: #1f242d; --border2: #262c36; --border3: #2c3441;
  --text: #e7eaf0; --text2: #aab2c0; --text3: #8b94a5; --text4: #59627a;
  --accent: #f0b323; --accentText: #0e1116; --roomNum: #f0b323; --sel: #1a1f28;
  --outBg: #2b3a55; --outText: #e7eaf0;
  --autoBg: #1a1f28; --autoText: #aab2c0; --autoBorder: #2c3441;
  --noteBg: #2a2410; --noteBorder: #5a4a12; --noteText: #f5dfa0; --noteIcon: #f0b323;
  --okBg: #12301f; --okText: #4ade80; --okBorder: #1f5a3a; --okBtn: #4ade80;
  --okBtnText: #0e1116; --okBanner: #d1fae5;
  --warnBg: #3a2a10; --warnText: #f0b323;
  --dangerBg: #3a1418; --dangerText: #ff5d5d; --danger: #ff5d5d;
  --presenceBg: #2a2140; --presenceText: #c4b5fd; --presenceAv: #a78bfa;
  --avMuted: #8b94a5; --avText: #0e1116;
  --tagBg: #1f242d; --tagText: #8b94a5;
  --timerDoneBg: #161a21; --timerDoneText: #8b94a5;
}

[data-theme='light'] {
  --bg: #f2f4f7; --bg2: #f7f8fa; --nav: #ffffff; --surface: #ffffff;
  --surface2: #eef1f5; --border: #dfe3ea; --border2: #d3d9e2; --border3: #c5ccd8;
  --text: #0e1116; --text2: #3d4655; --text3: #6b7486; --text4: #9aa3b2;
  --accent: #f0b323; --accentText: #0e1116; --roomNum: #9a6b00; --sel: #fff7e0;
  --outBg: #2b3a55; --outText: #ffffff;
  --autoBg: #eef1f5; --autoText: #3d4655; --autoBorder: #d3d9e2;
  --noteBg: #fff8e1; --noteBorder: #e6c96a; --noteText: #5c4300; --noteIcon: #9a6b00;
  --okBg: #e3f7ea; --okText: #15803d; --okBorder: #a7e3bd; --okBtn: #15803d;
  --okBtnText: #ffffff; --okBanner: #064e3b;
  --warnBg: #fff1cf; --warnText: #8a5a10;
  --dangerBg: #fde4e4; --dangerText: #b91c1c; --danger: #dc2626;
  --presenceBg: #ede9fe; --presenceText: #5b21b6; --presenceAv: #7c3aed;
  --avMuted: #6b7486; --avText: #ffffff;
  --tagBg: #eef1f5; --tagText: #6b7486;
  --timerDoneBg: #eef1f5; --timerDoneText: #9aa3b2;
}

@layer base {
  html, body, #root { height: 100%; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Grotesk', 'Segoe UI', system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  /* 44px controls, 8-10px radii, 1px borders, no shadows - mockup shape language. */
  button:focus-visible, a:focus-visible, input:focus-visible,
  textarea:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
}
```

- [ ] **Step 5: Write the failing token test**

The point of this test is that a later task cannot quietly drop or recolour a token. It reads the CSS as text — jsdom does not apply Vite's stylesheet, so asserting on `getComputedStyle` would pass vacuously.

`web/src/index.css.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')

const TOKENS = [
  'bg', 'bg2', 'nav', 'surface', 'surface2', 'border', 'border2', 'border3',
  'text', 'text2', 'text3', 'text4', 'accent', 'accentText', 'roomNum', 'sel',
  'outBg', 'outText', 'autoBg', 'autoText', 'autoBorder',
  'noteBg', 'noteBorder', 'noteText', 'noteIcon',
  'okBg', 'okText', 'okBorder', 'okBtn', 'okBtnText', 'okBanner',
  'warnBg', 'warnText', 'dangerBg', 'dangerText', 'danger',
  'presenceBg', 'presenceText', 'presenceAv',
  'avMuted', 'avText', 'tagBg', 'tagText', 'timerDoneBg', 'timerDoneText',
]

function block(selector: string): string {
  const start = css.indexOf(selector)
  expect(start, `${selector} block is missing`).toBeGreaterThan(-1)
  return css.slice(css.indexOf('{', start), css.indexOf('}', start))
}

describe('design tokens', () => {
  it('defines all 45 tokens in the dark (default) palette', () => {
    const dark = block(':root')
    for (const t of TOKENS) expect(dark, `--${t} missing from :root`).toContain(`--${t}:`)
  })

  it('redefines all 45 tokens in the light palette', () => {
    const light = block("[data-theme='light']")
    for (const t of TOKENS) expect(light, `--${t} missing from light`).toContain(`--${t}:`)
  })

  it('pins the approved accent and danger values in both palettes', () => {
    expect(block(':root')).toContain('--accent: #f0b323')
    expect(block("[data-theme='light']")).toContain('--accent: #f0b323')
    expect(block(':root')).toContain('--danger: #ff5d5d')
    expect(block("[data-theme='light']")).toContain('--danger: #dc2626')
  })

  it('has 45 tokens and no more, so a stray colour cannot sneak in', () => {
    const declared = new Set([...block(':root').matchAll(/--([a-zA-Z0-9]+):/g)].map((m) => m[1]))
    expect([...declared].sort()).toEqual([...TOKENS].sort())
  })
})
```

`web/src/lib/cn.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('joins truthy parts with a single space', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops false, null and undefined so conditionals read inline', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })

  it('returns an empty string when everything is falsy', () => {
    expect(cn(false, undefined)).toBe('')
  })
})
```

- [ ] **Step 6: Run the tests to verify they fail**

```bash
cd web && npm install && npm test
```

Expected: `cn.test.ts` FAILS to resolve `./cn`. `index.css.test.ts` passes once Step 4's CSS is in place — that is the correct intermediate state, not a problem.

- [ ] **Step 7: Write `web/src/lib/cn.ts`**

```ts
export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}
```

- [ ] **Step 8: Write `index.html`, `main.tsx` and a placeholder `App.tsx`**

`web/index.html` — the two font families from §5.0, preconnected so the first paint is not unstyled:

```html
<!doctype html>
<html lang="en" data-theme="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Harbourview — Guest Engagement</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500;600&display=swap"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/main.tsx`:

```tsx
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

`web/src/App.tsx` — a deliberate placeholder; Task 5 replaces its body with the provider stack. It renders one of each token role so Step 10 is a real visual check.

```tsx
export default function App() {
  return (
    <div className="min-h-full bg-bg p-8 font-ui text-text">
      <h1 className="text-2xl font-bold">Harbourview</h1>
      <p className="mt-2 text-text3">Scaffold is up.</p>
      <div className="mt-4 flex items-center gap-3">
        <span className="rounded bg-accent px-3 py-2 font-semibold text-accentText">Accent</span>
        <span className="rounded bg-okBg px-3 py-2 text-okText">ok</span>
        <span className="rounded bg-warnBg px-3 py-2 text-warnText">warn</span>
        <span className="rounded bg-dangerBg px-3 py-2 text-dangerText">danger</span>
        <span className="font-mono text-roomNum">412</span>
      </div>
    </div>
  )
}
```

`web/vitest.setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 7 tests across `index.css.test.ts` and `cn.test.ts`.

- [ ] **Step 10: Verify the build and a real page render**

```bash
cd web && npm run build
```

Expected: `tsc -b` clean, `vite build` writes `dist/`. Then `npm run dev` and load `http://localhost:5173` — the amber `Accent` pill, green `ok`, amber `warn`, red `danger` and the mono `412` all render on the near-black `--bg`. Set `data-theme="light"` on `<html>` in devtools and the page turns light with no other change. If a swatch is unstyled, Tailwind's `content` globs are wrong.

- [ ] **Step 11: Add the root scripts**

Modify the repo-root `package.json` to delegate into `web/` — keep the four existing scripts working. Note `schema` gains a redirect to the web tree, which is where §4.8 says the export lives:

```json
{
  "name": "concierge",
  "private": true,
  "scripts": {
    "server": "cd server && python run.py",
    "seed": "cd server && python -m seed.seed",
    "test:server": "cd server && python -m pytest -q",
    "schema": "cd server && python -m app.schemas.export_json_schema",
    "web": "cd web && npm run dev",
    "test:web": "cd web && npm test",
    "gen:types": "cd web && npm run gen:types",
    "dev": "echo Run npm run server and npm run web in two terminals"
  }
}
```

`schema` is left exactly as it was — the export module already writes `web/src/api/schema.json` and prints a log line, so adding a `>` redirect would overwrite the schema with `wrote <path>`.

`dev` is an instruction, not a launcher: the Flask dev server owns the reloader and the job worker, and wrapping both in one npm process makes a crashed worker silent. Two terminals is the honest interface.

- [ ] **Step 12: Commit**

```bash
git add web package.json
git commit -m "feat(web): scaffold Vite + React + Tailwind with the Night Shift tokens"
```

---

