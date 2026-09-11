import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// dirname(fileURLToPath(...)) rather than new URL('.', import.meta.url).pathname:
// on Windows the latter's pathname ("/C:/Users/...") makes node:path's join()
// prepend the current drive again, producing "C:\C:\Users\...\schema.json".
const here = dirname(fileURLToPath(import.meta.url))
const schema = join(here, 'schema.json')
const committed = join(here, 'types.generated.ts')

// Resolve json2ts's own CLI entrypoint (the file its "json2ts" bin points to)
// instead of shelling out to the npx shim: the package has no "exports" map,
// so its package.json resolves via plain Node module resolution, and its
// declared bin path is read from that same package.json rather than
// hard-coded, so this stays correct across upgrades. Running it directly
// with `node <entry>` needs no shell, which avoids Node's DEP0190 warning
// for passing an argv array together with shell:true.
const require = createRequire(import.meta.url)
const json2tsPackageJson = require.resolve('json-schema-to-typescript/package.json')
const json2tsBin = (require(json2tsPackageJson) as { bin: { json2ts: string } }).bin.json2ts
const json2tsCli = join(dirname(json2tsPackageJson), json2tsBin)

describe('generated API types', () => {
  it('are exactly what the generator produces from the committed schema', () => {
    const dir = mkdtempSync(join(tmpdir(), 'json2ts-'))
    try {
      const out = join(dir, 'types.ts')
      execFileSync(
        process.execPath,
        [json2tsCli, '--input', schema, '--output', out,
         '--style.singleQuote', '--no-additionalProperties', '--unreachableDefinitions'],
        { stdio: 'pipe' },
      )
      expect(readFileSync(committed, 'utf8')).toBe(readFileSync(out, 'utf8'))
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }, 60_000)

  it('exports the models the client depends on', () => {
    const src = readFileSync(committed, 'utf8')
    for (const name of [
      'SessionOut', 'ConversationSummary', 'ConversationDetail', 'MessageOut',
      'WorkOrderDetail', 'WorkOrderPrefill', 'QuickReplyOut', 'AssetOut',
      'NotificationOut', 'Overview', 'AgentStats', 'SimGuest', 'GuestThread',
    ]) {
      expect(src, `${name} was not generated`).toContain(`export interface ${name} `)
    }
  })
})
