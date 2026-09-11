# Task 3 Report: API client and query keys

## What I implemented

- `web/src/api/client.ts` — `ApiInit` type, `ApiError` class, `onUnauthorized()` global hook,
  `propertyPath()` helper, and the `api<T>()` fetch wrapper. Implemented exactly as specified in
  the brief (Step 3), verbatim.
- `web/src/api/queryKeys.ts` — the `qk` query-key factory, implemented exactly as specified in the
  brief (Step 4), verbatim. No imports from `client.ts` — it is a pure data module.
- `web/src/api/client.test.ts` — the 10-case test file from the brief (Step 1), verbatim.

No deviations from the brief were needed; no defects found in the brief's literal test code or
implementation.

## What I tested and the results

- Focused test: `npx vitest run src/api/client.test.ts` → 10/10 passed.
- Full suite: `npm test` → 4 test files, 19 tests, all passed (includes Task 1's `index.css.test.ts`
  and `cn.test.ts`, Task 2's `types.generated.test.ts`, and this task's `client.test.ts`).
- `npx tsc -b` → clean, no output, exit code 0.

## TDD evidence

**RED** — `cd web && npx vitest run src/api/client.test.ts` (run before `client.ts` existed):

```
FAIL src/api/client.test.ts [ src/api/client.test.ts ]
Error: Failed to resolve import "./client" from "src/api/client.test.ts". Does the file exist?
  Plugin: vite:import-analysis
 Test Files  1 failed (1)
      Tests  no tests
```

Expected failure: `./client` did not exist yet — exactly the "cannot resolve `./client`" failure
the brief predicted.

**GREEN** — `cd web && npx vitest run src/api/client.test.ts` (after writing `client.ts` and
`queryKeys.ts`):

```
✓ src/api/client.test.ts (10 tests) 9ms

 Test Files  1 passed (1)
      Tests  10 passed (10)
```

Full suite confirmation — `cd web && npm test`:

```
✓ src/index.css.test.ts (4 tests)
✓ src/api/client.test.ts (10 tests)
✓ src/lib/cn.test.ts (3 tests)
✓ src/api/types.generated.test.ts (2 tests)

 Test Files  4 passed (4)
      Tests  19 passed (19)
```

(The `DEP0190` warning is emitted by the pre-existing Task 2 generator test's child-process spawn,
not by anything added in this task.)

## `npx tsc -b`

Clean — no output, exit code 0.

## Files changed

- `web/src/api/client.ts` (new)
- `web/src/api/queryKeys.ts` (new)
- `web/src/api/client.test.ts` (new)

`git status --short` shows only these three untracked files; nothing else touched.

## Self-review findings

- **Completeness:** all 10 brief test cases present verbatim and all pass. `api()` handles 204
  (returns `undefined` without calling `.json()`), non-JSON error bodies (the `.json().catch(() =>
  null)` guard so an HTML 502 body still yields `ApiError` with `HTTP_502`), and network failures
  (the `try/catch` around the `fetch()` call producing `status: 0, code: 'NETWORK'`) as three
  distinct paths.
- **Quality:** `ApiError extends Error`, sets `this.name`, and `super(message)` gives it a real,
  usable `.message`. A raw `fetch` rejection (`TypeError`) never escapes — it's caught and
  rewrapped, verified by the network-failure test.
- **Discipline:** nothing beyond the brief was built — no retry policy, no hooks besides
  `onUnauthorized`, no raw `body` support on `ApiInit` (left as `Omit<RequestInit, 'body'>` per the
  scope note reserving that for Task 20). `queryKeys.ts` has zero imports, in particular none from
  `client.ts`.
- **Testing:** tests exercise real `fetch`/`Response` behavior via `vi.stubGlobal('fetch', ...)`
  and real `Response`/`Headers` objects rather than mocking `api()` internals. Test output is
  pristine — no unhandled rejections, no stray warnings attributable to this task's code.

## Issues or concerns

None. The brief's test code, implementation, and query-key factory were used verbatim with no
changes required.

## Commit

```
git add web/src/api/client.ts web/src/api/queryKeys.ts web/src/api/client.test.ts
git commit -m "feat(web): API client with typed ApiError, 204 handling and query keys"
```
