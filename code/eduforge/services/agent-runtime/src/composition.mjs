import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { serviceRoot } from './layout.mjs'

export function readComposition(profile = 'web') {
  if (!['web', 'sdk'].includes(profile)) throw new Error(`Unknown profile: ${profile}`)
  return JSON.parse(readFileSync(join(serviceRoot, 'config', `${profile}.json`), 'utf8'))
}
export function walkEntries(entries) {
  return entries.flatMap(row => [row, ...walkEntries(row.group ? row.config : row.config?.plugins ?? [])])
}
export function materializeComposition(profile, { labkitUrl }) {
  const rows = readComposition(profile)
  for (const row of walkEntries(rows)) {
    if (row.name === '@eduforge/labkit-plugin') {
      if (!labkitUrl?.startsWith('file:')) throw new Error('LabKit file URL required')
      row.name = labkitUrl
    }
  }
  return rows
}
