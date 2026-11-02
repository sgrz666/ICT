import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const serviceRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const repoRoot = resolve(serviceRoot, '../../../..')
export const sourceRoot = resolve(process.env.EDUFORGE_DSH_SOURCE || join(repoRoot, 'deep-agent/deepseek-harness'))
export function installationAnchor() {
  const packaged = join(serviceRoot, 'runtime', 'package.json')
  const anchor = existsSync(packaged) ? packaged : join(sourceRoot, 'apps/cli/package.json')
  if (!existsSync(anchor)) throw new Error(`DSH_NOT_BUILT: ${anchor}`)
  return anchor
}
export function runtimeRequire() { return createRequire(installationAnchor()) }
export async function runtimeImport(name, from) {
  const require = from ? createRequire(runtimeRequire().resolve(from)) : runtimeRequire()
  return import(pathToFileURL(require.resolve(name)).href)
}
export function labkitRoot() { return existsSync(join(serviceRoot, 'assets')) ? join(serviceRoot, 'assets') : repoRoot }
export function labkitEntry() { return join(labkitRoot(), 'deep-agent/local-tools/dsh-labkit/index.mjs') }
