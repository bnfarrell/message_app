# Task 1 Report: Scaffold, design tokens and Tailwind

## Status: DONE (fix round 1 applied — both Important findings resolved, see bottom of report)

Implemented all 12 steps of the brief. Two genuine plan/tooling defects were found and required
minimal, documented fixes to make Step 9 (`npm test`) and Step 10 (`npm run build`) pass as the
brief requires. No test assertions, token values, or hex colours were altered — the fixes are
scoped to build/test infrastructure only. Details below.

## What I implemented

All files exactly as listed in the brief:

- `web/package.json` — verbatim from Step 1, **plus one added devDependency** (see Defect 2 below).
- `web/vite.config.ts` — verbatim from Step 2, **plus one added test option** (see Defect 1 below).
- `web/tsconfig.json` — verbatim from Step 2, untouched.
- `web/tsconfig.node.json` — verbatim from Step 2 **except one compiler option** (see Defect 2 below).
- `web/postcss.config.js`, `web/.gitignore` (plus two extra ignore patterns, see Defect 2),
  `web/index.html`, `web/vitest.setup.ts` — verbatim.
- `web/tailwind.config.js` — verbatim from Step 3, all 45 token names, all colours resolved via `var(--name)`.
- `web/src/index.css` — verbatim from Step 4, both palettes copied character for character.
- `web/src/lib/cn.ts` — verbatim from Step 7.
- `web/src/main.tsx`, `web/src/App.tsx` — verbatim from Step 8.
- `web/src/index.css.test.ts`, `web/src/lib/cn.test.ts` — verbatim from Step 5, not modified.
- Root `package.json` — added `web`, `test:web`, `gen:types`, `dev` scripts exactly as given in
  Step 11. **`schema` script left byte-for-byte unchanged**, as instructed.

`web/src/api/schema.json` was not touched (confirmed already tracked in git, untouched by this task).

## Two defects found and how I handled them

Per the task instructions ("If a test in the brief seems to assert something wrong, do not bend
the code to make it pass. Report the defect... escalate rather than guessing if npm install fails
or a pinned version cannot resolve") I diagnosed both fully before acting, and in both cases chose
the smallest possible infrastructure fix that lets the brief's own literal test/build code run
unmodified, rather than editing any test assertion or token value. I'm flagging both explicitly as
concerns for review since they deviate from "use the exact values given."

### Defect 1: `index.css.test.ts` fails under the brief's own `vite.config.ts`

With `vite.config.ts` exactly as given (`environment: 'jsdom'` globally) and `index.css.test.ts`
exactly as given, the test throws `TypeError: The URL must be of scheme file`, not the CSS-content
assertions. Root cause: Vite's `new URL(relative, import.meta.url)` static-asset transform rewrites
the literal to a served URL (`http://localhost:3000/src/index.css`) whenever the module is
evaluated through Vite's browser-style transform pipeline, which Vitest uses for any environment
other than `node` (confirmed by reproducing the same file read under `--environment node`, where
`import.meta.url` resolves correctly to a `file://` URL and the read succeeds). This is not a CSS
content problem — I verified with `.txt` and other files that any relative `new URL(x, import.meta.url)` under jsdom hits the same rewrite. The brief's own Step 6 prediction ("index.css.test.ts
passes once Step 4's CSS is in place") does not hold under the pinned/resolved Vite 5.4.21 + Vitest
2.1.9 combination with a global jsdom environment.

**Fix applied:** added one line to the `test` block of `vite.config.ts` (not touching either of the
two call-outs the brief marks load-bearing):

```ts
environmentMatchGlobs: [['src/index.css.test.ts', 'node']],
```

This routes only this one file to Vitest's `node` environment (a supported, standard Vitest
mechanism for per-file environment overrides) while leaving `jsdom` as the default for every other
test — which future tasks doing React component testing will need. No test file content was
changed.

### Defect 2: `npm run build` fails against the brief's own `tsconfig.node.json` / `package.json`

`tsc -b` failed with two errors, both real, both root causes external to any code I wrote:

1. `error TS2688: Cannot find type definition file for 'node'` — `tsconfig.node.json` declares
   `"types": ["node"]` but the brief's Step 1 `package.json` devDependencies never lists
   `@types/node`, so no such type package is installed.
2. `tsconfig.json(21,18): error TS6310: Referenced project '...tsconfig.node.json' may not disable
   emit.` — `tsconfig.node.json` sets `"composite": true` and `"noEmit": true` together. TypeScript
   disallows a project referenced via `references` (which `tsconfig.json` does, pointing at
   `tsconfig.node.json`) from disabling emit, because the referencing project needs the referenced
   project's declaration/tsbuildinfo output to type-check incrementally against. This combination
   cannot ever produce a clean `tsc -b`, independent of dependency versions.

**Fixes applied (both minimal, both isolated to the two implicated files):**

- Added `"@types/node": "^20.16.5"` to `web/package.json` devDependencies (Node 20+ is the stated
  floor for this project).
- Changed `"noEmit": true` to `"emitDeclarationOnly": true` in `web/tsconfig.node.json`. This keeps
  `tsc -b` from emitting compiled `.js` for `vite.config.ts` (which is never meant to be bundled
  output) while still emitting the `.d.ts`/`.tsbuildinfo` that the composite/reference mechanism
  requires, which resolves TS6310 without touching `tsconfig.json`'s `references` array or
  `tsconfig.node.json`'s `composite` flag (both explicitly load-bearing per the brief's structure).
- Added `*.tsbuildinfo` and `vite.config.d.ts` to `web/.gitignore` — `tsc -b`'s composite build now
  writes these two stray artifacts into `web/` on every build; they are build output, not source,
  and were not previously covered by the brief's `.gitignore` list. Confirmed via `git status` that
  no stray files are staged after a full build.

No dependency versions given in the brief were changed; `@types/node` is a strictly additive
package required to make the brief's own `"types": ["node"]` declaration resolvable.

## TDD evidence

**RED** — `cd web && npm install && npm test` (after Step 1-6, before Step 7's `cn.ts` existed;
`vite.config.ts` already carried the Defect 1 fix at this point since the defect surfaces
regardless of implementation state):

```
❯ src/index.css.test.ts (4 tests)  [PASS — correct intermediate state per brief]
❯ src/lib/cn.test.ts (0 test)

FAIL src/lib/cn.test.ts [ src/lib/cn.test.ts ]
Error: Failed to resolve import "./cn" from "src/lib/cn.test.ts". Does the file exist?

 Test Files  1 failed | 1 passed (2)
      Tests  4 passed (4)
```

This is the expected failure: `cn.ts` did not exist yet, so Vite's import-analysis plugin cannot
resolve `./cn` from the test file. `index.css.test.ts` passing here (4/4) is the correct
intermediate state the brief calls out, not a defect — the CSS file was already written in Step 4.

**GREEN** — after Step 7 (`cn.ts` written): `cd web && npm test`

```
✓ src/index.css.test.ts (4 tests) 3ms
✓ src/lib/cn.test.ts (3 tests) 1ms

 Test Files  2 passed (2)
      Tests  7 passed (7)
```

Matches the brief's Step 9 expectation exactly: 7 tests across the two files, pristine output, no
warnings.

## Build verification (Step 10)

```
cd web && npm run build
```

```
tsc -b   -> clean, no errors
vite v5.4.21 building for production...
✓ 31 modules transformed.
dist/index.html                  0.75 kB │ gzip:  0.42 kB
dist/assets/index-CjZZXTGr.css   7.98 kB │ gzip:  2.44 kB
dist/assets/index-DefhLnz4.js  143.30 kB │ gzip: 46.01 kB
✓ built in 828ms
```

I cannot load the page in a browser, so per the task instructions I instead grepped the built CSS:

- `grep -o '#f0b323' dist/assets/*.css | wc -l` → **5 matches** (dark `:root` declaration, light
  block declaration, and Tailwind utility classes that reference it via `var(--accent)` — the
  utility classes themselves reference the custom property, not the literal, so the 5 literal hits
  are the two palette declarations plus token duplication inside Tailwind's generated output for
  `accent`/`accentText`/`roomNum` sharing the value).
- Light palette block confirmed present and intact in the bundle:
  `[data-theme=light]{--bg: #f2f4f7;--bg2: #f7f8fa;--nav: #ffffff;...--accent: #f0b323;...}` (full
  45-token block verified present).
- Spot-checked generated utility classes resolve through the custom properties, not literals:
  `.bg-accent{background-color:var(--accent)}`, `.text-roomNum{color:var(--roomNum)}`,
  `.bg-dangerBg{background-color:var(--dangerBg)}`.
- Both font families present: `font-family:Space Grotesk,Segoe UI,system-ui,sans-serif` and
  `font-family:JetBrains Mono,Consolas,monospace`.

I did not run `npm run dev` or open a browser, and I am not claiming any visual verification — only
the grep evidence above.

## Files changed

Created (all under `web/`, matching the brief's file list exactly):
- `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.node.json`,
  `web/tailwind.config.js`, `web/postcss.config.js`, `web/index.html`, `web/.gitignore`,
  `web/vitest.setup.ts`
- `web/src/index.css`, `web/src/lib/cn.ts`, `web/src/main.tsx`, `web/src/App.tsx`
- `web/src/index.css.test.ts`, `web/src/lib/cn.test.ts`
- `web/package-lock.json` (byproduct of `npm install`, conventionally committed alongside `package.json`)

Modified:
- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\package.json` — added `web`, `test:web`,
  `gen:types`, `dev` scripts; `schema` left unchanged.

Deviations from the brief's literal file contents (both documented above as defects):
- `web/vite.config.ts` — one added line (`environmentMatchGlobs`).
- `web/tsconfig.node.json` — `noEmit: true` → `emitDeclarationOnly: true`.
- `web/package.json` — added `@types/node` devDependency.
- `web/.gitignore` — added `*.tsbuildinfo` and `vite.config.d.ts`.

## Self-review findings

- All 45 tokens present, spelled identically, in both `tailwind.config.js`'s `tokens` array and
  both palette blocks in `index.css` — verified by the "45 tokens and no more" test passing.
- `--accent: #f0b323` and `--danger` (`#ff5d5d` dark / `#dc2626` light) pinned correctly in both
  palettes, matching the test's explicit assertions.
- No `theme.extend.colors` entry holds a literal hex — all resolve through `var(--token)`, confirmed
  both in source and in the built CSS.
- No `any` used anywhere; no `@ts-ignore` anywhere.
- `tsc -b` clean, `strict: true` intact and unmodified in `tsconfig.json`.
- Test output is pristine — no console warnings, no act() warnings, no stray logs — for both the
  RED and GREEN runs.
- No extra files created beyond the brief's list (aside from `package-lock.json`, a standard
  `npm install` byproduct, and the two build-artifact patterns added to `.gitignore`).
- No component library, no charting library, no extra runtime dependencies added — the only
  addition is `@types/node`, a type-only devDependency required by the brief's own
  `tsconfig.node.json`.
- Confirmed `git status` shows only the exact file set expected (plus `package-lock.json`); no
  `node_modules/`, `dist/`, `.tsbuildinfo`, or `vite.config.d.ts` staged.
- Confirmed `web/src/api/schema.json` untouched and still the sole pre-existing tracked file under
  `web/`.

## Issues / concerns for the reviewer

1. **`vite.config.ts` and `tsconfig.node.json` are no longer byte-for-byte identical to the brief.**
   Both deviations are one line each, both are standard/idiomatic fixes for real tooling
   incompatibilities (not stylistic preferences), and neither touches the two call-outs the brief
   marks explicitly load-bearing. I believe these are the correct calls, but they are deviations
   from "use the exact values it gives," so I'm flagging prominently rather than treating it as a
   silent judgment call.
2. **`@types/node` version (`^20.16.5`) was not specified anywhere in the brief** — I chose a Node
   20 LTS-era version consistent with the stated "Node 20+" floor and the Vite 5.4.x/2024-era
   dependency set. If the plan author wants a different pin, this is a one-line change.
3. Did not run `npm run dev` / open a browser, per the task's own instruction that I cannot do so —
   relied on the `dist/` CSS grep instead, as directed.

---

## Fix round 1: review findings

The review accepted all three tooling deviations (`environmentMatchGlobs`, `@types/node`,
`emitDeclarationOnly`) and returned two Important findings. Both fixed; neither loosens or reverts
anything already accepted.

### Finding 1 — `.gitignore` misses `playwright.config.d.ts`

`web/tsconfig.node.json`'s `include` already lists both `vite.config.ts` and
`playwright.config.ts`. With `composite: true` + `emitDeclarationOnly: true` and no `outDir`,
`tsc -b` emits a `.d.ts` beside every included source file that exists. `playwright.config.ts`
doesn't exist yet (Task 21 owns it), so TS silently skips the missing entry today — but once that
file lands, `tsc -b` will emit an ungitignored `web/playwright.config.d.ts`.

**Fix:** replaced the literal `vite.config.d.ts` entry with one anchored pattern:

```diff
-vite.config.d.ts
+/*.config.d.ts
```

The leading `/` anchors the pattern to `web/`'s root (where `.gitignore` lives); `*` does not match
`/` in gitignore glob syntax, so this covers any current or future root-level `*.config.d.ts`
(`vite.config.d.ts`, `playwright.config.d.ts`, etc.) without touching declaration files nested
under `src/`.

**Verification performed** (Finding 1):

```bash
cd web
rm -f *.tsbuildinfo vite.config.d.ts playwright.config.d.ts
touch playwright.config.ts        # simulates Task 21 landing
npx tsc -b
ls *.d.ts
```
Output: `playwright.config.d.ts` and `vite.config.d.ts` both generated (`tsc -b` clean).

```bash
cd ..
git status --short
```
Output:
```
 M web/.gitignore
 M web/src/index.css.test.ts
?? web/playwright.config.ts
```
Neither generated `.d.ts` file appears — the ignore covers both. Cleaned up afterward:

```bash
cd web
rm -f playwright.config.ts playwright.config.d.ts vite.config.d.ts *.tsbuildinfo
cd ..
git status --short
```
Output: only the two intended fix files remain modified (`web/.gitignore`,
`web/src/index.css.test.ts`); `playwright.config.ts` is gone, as instructed — Task 21 owns its
creation, not this fix round.

### Finding 2 — the "no stray colour" test only bounded the dark palette

`index.css.test.ts`'s last case built its `declared` set from `block(':root')` only, so a 46th
token added solely under `[data-theme='light']` would pass every existing assertion. Per the
plan/controller ruling, both palettes must be bounded.

**Fix:** factored the "declared token set" extraction into a small local closure (no new
abstraction, no extra file) and asserted it against `TOKENS` for both selectors:

```ts
it('has 45 tokens and no more, so a stray colour cannot sneak in', () => {
  const declaredTokens = (selector: string) =>
    [...new Set([...block(selector).matchAll(/--([a-zA-Z0-9]+):/g)].map((m) => m[1]))].sort()

  expect(declaredTokens(':root')).toEqual([...TOKENS].sort())
  expect(declaredTokens("[data-theme='light']")).toEqual([...TOKENS].sort())
})
```

**Covering test run** (Finding 2), after the fix:

```
$ npx vitest run src/index.css.test.ts
✓ src/index.css.test.ts (4 tests) 3ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

**Deliberate-failure evidence** — proving the new assertion can actually fail, not just pass
vacuously. Temporarily added a 46th token to the light block only
(`web/src/index.css`, inside `[data-theme='light']`): `--strayColour: #ff00ff;`, then re-ran the
same test:

```
$ npx vitest run src/index.css.test.ts
❯ src/index.css.test.ts (4 tests | 1 failed)
  × design tokens > has 45 tokens and no more, so a stray colour cannot sneak in
    → expected [ 'accent', 'accentText', …(44) ] to deeply equal [ 'accent', 'accentText', …(43) ]
    + "strayColour" (unexpected, present only in received array)
 Test Files  1 failed (1)
      Tests  1 failed | 3 passed (4)
```

The other three cases in the file kept passing (the stray token doesn't violate their `toContain`
checks), confirming this new assertion — and only this one — is what catches a light-only stray
token. Removed `--strayColour: #ff00ff;` immediately after, and re-ran to confirm clean green:

```
$ npx vitest run src/index.css.test.ts
✓ src/index.css.test.ts (4 tests) 3ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

### Full suite before committing

```bash
cd web && npm test
```
```
✓ src/index.css.test.ts (4 tests) 3ms
✓ src/api/types.generated.test.ts (2 tests) 2600ms
✓ src/lib/cn.test.ts (3 tests) 2ms

 Test Files  3 passed (3)
      Tests  9 passed (9)
```

Note: `src/api/types.generated.test.ts` and its one Node child-process deprecation warning
(`DEP0190`) come from Task 2 (`feat(web): generate API types from the committed schema...`,
commit `6e82824`), which landed in this working tree between my original Task 1 commit and this fix
round. That file and warning are outside Task 1's scope — I did not touch it, and confirmed via
`git diff` that my staged changes touch only `web/.gitignore` and `web/src/index.css.test.ts`.

### Files changed (fix round 1)

- `web/.gitignore` — `vite.config.d.ts` → `/*.config.d.ts`.
- `web/src/index.css.test.ts` — bounded the light palette's declared-token set alongside `:root`'s.

### Commit

`e796486` — `fix(web): gitignore playwright.config.d.ts and bound the light palette's token set`
