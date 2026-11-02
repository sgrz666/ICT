import { cpSync, existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'

const identity = path => realpathSync(path)
const readManifest = dir => JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))

/** Resolve from the declaring package, preserving pnpm's actual instance identity. */
export function resolvePackageDirectory(name, fromDir, workspace = new Map()) {
  if (workspace.has(name)) return identity(workspace.get(name))
  for (let dir = resolve(fromDir); ; dir = dirname(dir)) {
    const candidate = join(dir, 'node_modules', name)
    if (existsSync(join(candidate, 'package.json'))) return identity(candidate)
    if (dirname(dir) === dir) return undefined
  }
}

function supports(values, target) {
  if (!Array.isArray(values) || values.length === 0) return true
  if (values.includes(`!${target}`)) return false
  const positive = values.filter(value => !value.startsWith('!'))
  return positive.length === 0 || positive.includes(target) || positive.includes('any')
}

/** Read only named dependency manifests, never traverse the installation's node_modules. */
export function collectPackageGraph({ seeds, workspace = new Map(), manifestTransform = value => value, platform = process.platform, arch = process.arch }) {
  const nodes = new Map(), skipped = []
  const visit = (directory, optional = false) => {
    const id = identity(directory)
    if (nodes.has(id)) return id
    const original = readManifest(id)
    if (!supports(original.os, platform) || !supports(original.cpu, arch)) {
      if (!optional) throw new Error(`Unsupported required package: ${original.name} (${platform}/${arch})`)
      skipped.push({ name: original.name, reason: 'other platform' })
      return undefined
    }
    const manifest = manifestTransform(structuredClone(original), id)
    const node = { id, name: manifest.name, version: manifest.version, manifest, original, dependencies: new Map(), workspace: workspace.has(manifest.name) }
    nodes.set(id, node)
    for (const section of ['dependencies', 'optionalDependencies', 'peerDependencies']) {
      for (const name of Object.keys(manifest[section] || {})) {
        const maySkip = section === 'optionalDependencies' || section === 'peerDependencies' && manifest.peerDependenciesMeta?.[name]?.optional === true
        const dependency = resolvePackageDirectory(name, id, workspace)
        if (!dependency) {
          if (!maySkip) throw new Error(`Missing required dependency: ${node.name} -> ${name}`)
          skipped.push({ name, parent: node.name, reason: 'optional dependency absent' })
          continue
        }
        const target = visit(dependency, maySkip)
        if (target) node.dependencies.set(name, target)
      }
    }
    return id
  }
  const rootIds = seeds.map(directory => visit(directory)).filter(Boolean)
  return { nodes, rootIds, skipped }
}

export function copyDependencyFiles(node, destination) {
  cpSync(node.id, destination, { recursive: true, dereference: true, filter: source => {
    const parts = relative(node.id, source).split(/[\\/]/)
    return !parts.some(part => part === 'node_modules' || part === '.git' || part === '.env' || part.startsWith('.env.'))
  } })
}

/** Build a portable physical npm tree; incompatible instances get nearest nested placements. */
export function materializePackageGraph({ graph, outDir, copyPackage = copyDependencyFiles }) {
  const modules = join(resolve(outDir), 'node_modules')
  mkdirSync(modules, { recursive: true })
  const placements = new Map(), pending = [], canonical = new Map()
  const place = (id, path) => {
    if (placements.has(path)) {
      if (placements.get(path) !== id) throw new Error(`Package placement collision: ${path}`)
      return
    }
    placements.set(path, id)
    const node = graph.nodes.get(id)
    copyPackage(node, path)
    const manifest = structuredClone(node.manifest)
    for (const section of ['dependencies', 'optionalDependencies', 'peerDependencies']) {
      for (const [name, value] of Object.entries(manifest[section] || {})) {
        if (/^(workspace:|link:|file:)/.test(value)) {
          const dep = graph.nodes.get(node.dependencies.get(name))
          if (dep) manifest[section][name] = dep.version
          else delete manifest[section][name]
        }
      }
    }
    writeFileSync(join(path, 'package.json'), JSON.stringify(manifest, null, 2) + '\n')
    pending.push(path)
  }
  // Register every canonical instance before adding nested versions; this avoids order-dependent copies.
  for (const [id, node] of graph.nodes) if (!canonical.has(node.name)) canonical.set(node.name, id)
  for (const [name, id] of canonical) place(id, join(modules, name))
  const lookup = (from, name) => {
    for (let dir = from; ; dir = dirname(dir)) {
      const found = placements.get(join(dir, 'node_modules', name))
      if (found) return found
      if (dirname(dir) === dir) return undefined
    }
  }
  for (let index = 0; index < pending.length; index++) {
    const path = pending[index], node = graph.nodes.get(placements.get(path))
    for (const [name, target] of node.dependencies) {
      if (lookup(path, name) !== target) place(target, join(path, 'node_modules', name))
    }
    if (pending.length > graph.nodes.size * 20) throw new Error('Dependency placement failed to converge')
  }
  const resolutionErrors = []
  for (const [path, id] of placements) for (const [name, target] of graph.nodes.get(id).dependencies) {
    if (lookup(path, name) !== target) resolutionErrors.push(`${relative(outDir, path)} -> ${name}`)
  }
  if (resolutionErrors.length) throw new Error(`Packaged dependency resolution mismatch: ${resolutionErrors.join(', ')}`)
  return { placements, canonical, resolutionErrors }
}
