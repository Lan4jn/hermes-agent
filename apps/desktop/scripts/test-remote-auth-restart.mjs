import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, realpathSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const desktop = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const electron = process.argv[2]

if (!electron) {
  throw new Error('Usage: node scripts/test-remote-auth-restart.mjs <path-to-electron-executable>')
}

const root = mkdtempSync(join(tmpdir(), 'hermes-auth-restart-'))
const fixture = join(root, 'fixture.cjs')
const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE

function run(command, args) {
  const result = spawnSync(command, args, { cwd: desktop, stdio: 'inherit', env, timeout: 90_000 })

  assert.equal(result.error, undefined, 'test process must launch and finish')
  assert.equal(result.status, 0, `test process failed: ${result.status}`)
}

run(process.execPath, [
  '../../node_modules/esbuild/bin/esbuild',
  'electron/remote-auth-restart-fixture/main.ts',
  '--bundle',
  '--platform=node',
  '--external:electron',
  '--format=cjs',
  `--outfile=${fixture}`
])
run(resolve(electron), [fixture, root, 'login'])
run(resolve(electron), [fixture, root, 'restore'])
console.log('REMOTE_AUTH_PROCESS_RESTART_PASS')

// Only remove the newly-created, verified test directory, never userData.
assert.equal(realpathSync(root), realpathSync(resolve(root)))
assert.equal(dirname(root), tmpdir())
assert.ok(root.startsWith(join(tmpdir(), 'hermes-auth-restart-')))
rmSync(root, { recursive: true, force: true })
