import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync } from 'node:fs'
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

describe('generated API types', () => {
  it('are exactly what the generator produces from the committed schema', () => {
    const out = join(mkdtempSync(join(tmpdir(), 'json2ts-')), 'types.ts')
    execFileSync(
      'npx',
      ['json2ts', '--input', schema, '--output', out,
       '--style.singleQuote', '--no-additionalProperties', '--unreachableDefinitions'],
      { stdio: 'pipe', shell: process.platform === 'win32' },
    )
    expect(readFileSync(committed, 'utf8')).toBe(readFileSync(out, 'utf8'))
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
