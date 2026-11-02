import { createHash } from 'node:crypto'
import { copyFileSync, cpSync, createReadStream, existsSync, globSync, lstatSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { basename, dirname, join, relative, resolve, sep } from 'node:path'
import { repoRoot, serviceRoot, sourceRoot } from './layout.mjs'
import { collectPackageGraph, materializePackageGraph, resolvePackageDirectory } from './package-graph.mjs'

const readJson = file => JSON.parse(readFileSync(file, 'utf8'))
const writeJson = (file, value) => { mkdirSync(dirname(file), { recursive: true }); writeFileSync(file, JSON.stringify(value, null, 2) + '\n') }
const portable = value => value.split(sep).join('/')
const CLI_DEPS = ['@deepseek-ai/dsh-app-boot', '@deepseek-ai/dsh-home-paths', '@deepseek-ai/dsh-http-proxy', '@deepseek-ai/dsh-launch-environment', '@deepseek-ai/dsh-cmdline']
const WEB_DEPS = ['@deepseek-ai/schemastery', '@deepseek-ai/dsh-app-boot', '@deepseek-ai/dsh-host-frontend-static', '@deepseek-ai/dsh-host-webserver', '@deepseek-ai/dsh-launch-environment', '@deepseek-ai/dsh-subprocess', '@deepseek-ai/dsh-web-frontend', '@deepseek-ai/dsh-cmdline', 'commander', 'open']
const FORBIDDEN_PACKAGES = /(?:libreoffice|dsh-(?:skill-office|office-to-pdf|experimental-|swe)|^@openai\/codex(?:-|$)|^@anthropic-ai\/claude-agent-sdk|^(?:typescript|tsx|vitest|electron|vite|pnpm)$)/

function workspacePackages() {
  const result = new Map()
  for (const file of globSync(['vendor/*/package.json', 'packages/*/*/package.json', 'apps/*/package.json', 'native/system/packages/*/package.json'], { cwd: sourceRoot })) {
    const path = join(sourceRoot, file), manifest = readJson(path)
    if (manifest.name) result.set(manifest.name, dirname(path))
  }
  return result
}

/** Only deployment copies lose product-wide dependency declarations. */
function runtimeManifest(manifest) {
  if (manifest.name === '@deepseek-ai/dsh') {
    manifest.dependencies = Object.fromEntries(CLI_DEPS.map(name => [name, manifest.dependencies[name]]))
    manifest.exports = { './profile-boot': './lib/profile-boot.js', './package.json': './package.json' }
    delete manifest.bin
    manifest.files = ['lib/profile-boot.js', 'lib/profile-boot-*.js']
  } else if (manifest.name === '@deepseek-ai/dsh-web-app') {
    manifest.dependencies = Object.fromEntries(WEB_DEPS.map(name => [name, manifest.dependencies[name]]))
    delete manifest.dsh?.bundle
    manifest.files = manifest.files.filter(value => !value.endsWith('.yml'))
  } else if (manifest.name === '@deepseek-ai/dsh-sdk-app') {
    manifest.dependencies = Object.fromEntries(['@deepseek-ai/dsh-cmdline', '@deepseek-ai/schemastery', 'commander'].map(name => [name, manifest.dependencies[name]]))
    delete manifest.dsh?.bundle
    manifest.files = manifest.files.filter(value => !value.endsWith('.yml'))
  }
  delete manifest.devDependencies
  delete manifest.scripts
  delete manifest.workspaces
  delete manifest.packageManager
  for (const name of Object.keys(manifest.peerDependencies || {})) if (name.startsWith('@types/')) {
    delete manifest.peerDependencies[name]
    if (manifest.peerDependenciesMeta) delete manifest.peerDependenciesMeta[name]
  }
  for (const key of Object.keys(manifest)) if (key.startsWith('_')) delete manifest[key]
  return manifest
}

function seedNames() {
  const names = new Set(['@deepseek-ai/dsh', '@deepseek-ai/dsh-app-boot', '@deepseek-ai/cordis-plugin-include', '@deepseek-ai/dsh-tools', 'js-yaml'])
  const visit = value => {
    if (Array.isArray(value)) { for (const item of value) visit(item); return }
    if (!value || typeof value !== 'object') return
    if (value.disabled === true || value.disabled?.__jsExpr?.trim() === "process.platform === 'win32'") return
    if (typeof value.name === 'string' && value.name.startsWith('@deepseek-ai/')) names.add(value.name.split('/').slice(0, 2).join('/'))
    for (const item of Object.values(value)) visit(item)
  }
  for (const profile of ['web', 'sdk']) visit(readJson(join(serviceRoot, 'config', `${profile}.json`)))
  return [...names].sort()
}

function isRuntimeFile(source, root, { external = false } = {}) {
  const path = portable(relative(root, source)), parts = path.split('/')
  if (parts.some(part => ['node_modules', '.git', '.cache', '__pycache__', '.pytest_cache'].includes(part) || part === '.env' || part.startsWith('.env.'))) return false
  const prebuild=parts.indexOf('prebuilds')
  if(prebuild>=0 && parts[prebuild+1] && parts[prebuild+1]!=='win32-x64')return false
  if (/(?:\.map|\.tsbuildinfo|\.d\.[cm]?ts|\.pdb)$/i.test(path)) return false
  if (/\.log$/i.test(path)) return false
  if (!external && parts[0] === 'src') return false
  return true
}

function copyTree(source, destination, options = {}) {
  if (!existsSync(source)) throw new Error(`Required package asset is missing: ${source}`)
  mkdirSync(dirname(destination), { recursive: true })
  cpSync(source, destination, { recursive: true, dereference: true, filter: path => isRuntimeFile(path, source, options) })
}

function copyRuntimePackage(node, destination) {
  mkdirSync(destination, { recursive: true })
  if (!node.workspace) {
    copyTree(node.id, destination, { external: true })
    return
  }
  const patterns = (node.manifest.files || ['lib']).filter(value => !value.startsWith('!') && !value.startsWith('src'))
  const negative = (node.manifest.files || []).filter(value => value.startsWith('!')).map(value => value.slice(1))
  const excluded = new Set(globSync(negative, { cwd: node.id }))
  for (const file of globSync([...patterns, 'LICENSE*', 'NOTICE*', 'README.md'], { cwd: node.id })) {
    if (excluded.has(file) || !isRuntimeFile(join(node.id, file), node.id)) continue
    const source = join(node.id, file), destinationFile = join(destination, file)
    if (statSync(source).isDirectory()) cpSync(source, destinationFile, { recursive: true, dereference: true, filter: candidate => {
      const path = relative(node.id, candidate)
      return isRuntimeFile(candidate, node.id) && ![...excluded].some(exclusion => path === exclusion || path.startsWith(exclusion + sep))
    } })
    else { mkdirSync(dirname(destinationFile), { recursive: true }); copyFileSync(source, destinationFile) }
  }
  if (node.name === '@deepseek-ai/dsh-web-frontend' && !existsSync(join(destination, 'dist', 'index.html'))) throw new Error('Built Web frontend dist/index.html is missing')
}

function writeOwnedReadmes(root, label) {
  const visit = dir => {
    const children = readdirSync(dir, { withFileTypes: true })
    if (!existsSync(join(dir, 'README.md'))) writeFileSync(join(dir, 'README.md'), `# ${label}\n\n职责：独立运行包中的 ${portable(relative(root, dir)) || label}。\n\n内容：${children.map(entry => `\`${entry.name}\``).join('、')}。\n\n与上下层的关系：由发布器从选定运行文件复制，供包内启动器或 LabKit 使用。\n\n已知的坑与纪律：这是生成产物；依赖目录由包根 inventory.json 记录，勿手工修改。\n`)
    for (const child of children) if (child.isDirectory() && !['node_modules', 'browsers'].includes(child.name)) visit(join(dir, child.name))
  }
  visit(root)
}

function portableReadmeLinks(output) {
  const visit = dir => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) { if (!['node_modules', 'browsers', 'runtime'].includes(entry.name)) visit(path); continue }
      if (entry.name !== 'README.md') continue
      const rel = relative(output, path), asset = rel.startsWith('assets' + sep)
      const source = asset ? join(repoRoot, relative(join(output, 'assets'), path)) : join(serviceRoot, rel)
      if (!existsSync(source)) continue
      const rewritten = readFileSync(path, 'utf8').replace(/\[([^\]]+)\]\(([^)]+)\)/g, (original, label, target) => {
        if (/^(?:https?:|mailto:|#)/.test(target)) return original
        const [local, fragment] = target.split('#')
        const sourceTarget = resolve(dirname(source), local)
        let copied
        if (sourceTarget === serviceRoot || sourceTarget.startsWith(serviceRoot + sep)) copied = join(output, relative(serviceRoot, sourceTarget))
        else if (sourceTarget === repoRoot || sourceTarget.startsWith(repoRoot + sep)) copied = join(output, 'assets', relative(repoRoot, sourceTarget))
        return copied && existsSync(copied) ? `[${label}](${portable(relative(dirname(path), copied))}${fragment ? '#' + fragment : ''})` : `${label}（源码参考）`
      })
      writeFileSync(path, rewritten)
    }
  }
  visit(output)
}

function packageLabkit(output) {
  const assets = join(output, 'assets')
  const directories = [
    'deep-agent/local-tools/dsh-labkit', 'code/eduforge/tools/labkit',
    'code/eduforge/catalog/templates/mechanics/projectile', 'code/eduforge/catalog/templates/mechanics/pendulum',
    'code/eduforge/catalog/templates/circuits/ohms-law',
  ]
  for (const path of directories) copyTree(join(repoRoot, path), join(assets, path), { external: true })
  const evidence = 'source/library/circuit-lab-evidence.json'
  mkdirSync(dirname(join(assets, evidence)), { recursive: true })
  copyFileSync(join(repoRoot, evidence), join(assets, evidence))
  const sidecars = []
  for (const [path, name] of [['source/components', 'matter-js'], ['code/eduforge/services/engine-host', 'playwright']]) {
    const source = join(repoRoot, path), destination = join(assets, path)
    const pkg = resolvePackageDirectory(name, source)
    if (!pkg) throw new Error(`LabKit requires installed ${name}`)
    const graph = collectPackageGraph({ seeds: [pkg], manifestTransform: runtimeManifest })
    const manifest = readJson(join(source, 'package.json'))
    delete manifest.devDependencies
    delete manifest.scripts
    manifest.dependencies = { [name]: readJson(join(pkg, 'package.json')).version }
    writeJson(join(destination, 'package.json'), manifest)
    materializePackageGraph({ graph, outDir: destination, copyPackage: copyRuntimePackage })
    sidecars.push({ path, graph })
  }
  const playwright = sidecars.find(item => item.path.endsWith('engine-host')).graph
  const core = [...playwright.nodes.values()].find(node => node.name === 'playwright-core')
  if (!core) throw new Error('Playwright runtime closure has no playwright-core')
  const browserModule = createRequire(join(core.id, 'package.json'))(core.id)
  let installed = browserModule.chromium.executablePath()
  while (dirname(installed) !== installed && !/^chromium-\d+$/.test(basename(installed))) installed = dirname(installed)
  if (!/^chromium-\d+$/.test(basename(installed))) throw new Error('Cannot locate installed Chromium cache')
  const cache = dirname(installed), descriptors = readJson(join(core.id, 'browsers.json')).browsers
  const browsers = []
  // All owned probes run headless. The GUI is served to the user's browser;
  // shipping a second full Chrome installation would add unused duplicate binaries.
  for (const name of ['chromium-headless-shell', 'ffmpeg', 'winldd']) {
    const descriptor = descriptors.find(value => value.name === name)
    if (!descriptor) throw new Error(`Playwright browser descriptor missing: ${name}`)
    const directory = `${name.replaceAll('-', '_')}-${descriptor.revision}`
    if (!existsSync(join(cache, directory))) throw new Error(`Required browser cache missing: ${directory}; install the engine-host Chromium revision first`)
    copyTree(join(cache, directory), join(output, 'runtime', 'browsers', directory), { external: true })
    browsers.push({ name, revision: descriptor.revision, directory })
  }
  writeOwnedReadmes(assets, 'LabKit 运行资源')
  return { browsers, sidecarPackages: sidecars.flatMap(item => [...item.graph.nodes.values()].map(node => ({ name: node.name, version: node.version, owner: item.path }))) }
}

async function inventory(root) {
  const files = [], visit = async dir => {
    for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(dir, entry.name)
      if (lstatSync(path).isSymbolicLink()) throw new Error(`Nonportable symlink in package: ${relative(root, path)}`)
      if (entry.isDirectory()) await visit(path)
      else {
        const hash = createHash('sha256')
        for await (const chunk of createReadStream(path)) hash.update(chunk)
        files.push({ path: portable(relative(root, path)), bytes: statSync(path).size, sha256: hash.digest('hex') })
      }
    }
  }
  await visit(root)
  return files
}

export async function auditPackage(root) {
  const saved=readJson(join(root,'inventory.json'))
  const actual=(await inventory(root)).filter(f=>f.path!=='inventory.json')
  const expected=new Map(saved.files.map(f=>[f.path,f]))
  const changed=[],unexpected=[]
  for(const file of actual){
    const prior=expected.get(file.path)
    if(!prior)unexpected.push(file.path)
    else if(file.sha256!==prior.sha256||file.bytes!==prior.bytes)changed.push(file.path)
    expected.delete(file.path)
  }
  const missing=[...expected.keys()]
  return {ok:changed.length===0&&unexpected.length===0&&missing.length===0,changed,unexpected,missing,checked:actual.length}
}

/** Build once into a fresh directory; source checkout and previous outputs remain untouched. */
export async function buildPackage({ outDir } = {}) {
  const output = resolve(outDir || join(repoRoot, 'output/eduforge/candidates/agent-runtime', new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-')))
  if (existsSync(output)) throw new Error(`Output directory already exists: ${output}`)
  for (const protectedRoot of [sourceRoot, serviceRoot]) if (output === protectedRoot || output.startsWith(protectedRoot + sep)) throw new Error('Package output must be outside source and service directories')
  if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('This carrier packages only the current Windows x64 installation')
  if (!existsSync(join(serviceRoot, 'README.md'))) throw new Error('Service README.md must exist before packaging')
  const workspace = workspacePackages()
  const lock=readJson(join(serviceRoot,'config/upstream.lock.json'))
  const commit=execFileSync('git',['-C',sourceRoot,'rev-parse','HEAD'],{encoding:'utf8'}).trim()
  if(commit!==lock.commit)throw new Error(`UPSTREAM_DRIFT: expected ${lock.commit}, got ${commit}`)
  const seeds = seedNames().map(name => {
    const dir = resolvePackageDirectory(name, join(sourceRoot, 'apps', 'cli'), workspace)
    if (!dir) throw new Error(`Configuration package is not installed: ${name}`)
    return dir
  })
  const graph = collectPackageGraph({ seeds, workspace, manifestTransform: runtimeManifest })
  const forbidden = [...graph.nodes.values()].filter(node => FORBIDDEN_PACKAGES.test(node.name))
  if (forbidden.length) throw new Error(`Excluded package entered runtime closure: ${forbidden.map(node => `${node.name} (from ${[...graph.nodes.values()].filter(parent => [...parent.dependencies.values()].includes(node.id)).map(parent => parent.name).join(', ')})`).join('; ')}`)
  mkdirSync(dirname(output), { recursive: true })
  mkdirSync(output, { recursive: false })
  for (const name of ['src', 'config', 'tests']) copyTree(join(serviceRoot, name), join(output, name), { external: true })
  for (const name of ['agent-runtime.ps1', 'package.json', 'README.md']) copyFileSync(join(serviceRoot, name), join(output, name))
  const runtime = join(output, 'runtime')
  const materialized = materializePackageGraph({ graph, outDir: runtime, copyPackage: copyRuntimePackage })
  writeJson(join(runtime, 'package.json'), { name: '@eduforge/agent-runtime-installation', version: '0.1.0', private: true, type: 'module', dependencies: Object.fromEntries([...materialized.canonical].map(([name, id]) => [name, graph.nodes.get(id).version])) })
  copyFileSync(process.execPath, join(runtime, 'node.exe'))
  const nodeLicense=join(dirname(process.execPath),'LICENSE')
  if(existsSync(nodeLicense))copyFileSync(nodeLicense,join(runtime,'LICENSE.node.txt'))
  writeFileSync(join(runtime, 'README.md'), '# 原生运行依赖\n\n职责：提供 Node、Cordis 插件与浏览器运行环境。\n\n内容：`node.exe`、`package.json`、`node_modules/`、`browsers/`。\n\n与上下层的关系：由上层 `agent-runtime.ps1` 使用，完整文件哈希见 `../inventory.json`。\n\n已知的坑与纪律：实体 npm 依赖树支持目录移动；不含源码 checkout、用户凭据或开发依赖。浏览器由 `PLAYWRIGHT_BROWSERS_PATH` 指向本目录。\n')
  const assets = packageLabkit(output)
  portableReadmeLinks(output)
  const files = await inventory(output)
  const record = { schema: 'eduforge.agent-runtime.package/v1', created_at: new Date().toISOString(), platform: process.platform, arch: process.arch, node: process.version,
    upstream: readJson(join(serviceRoot, 'config/upstream.lock.json')), package_instances: graph.nodes.size, physical_package_placements: materialized.placements.size,
    packages: [...graph.nodes.values()].map(node => ({ name: node.name, version: node.version, workspace: node.workspace })).sort((a, b) => a.name.localeCompare(b.name)),
    ...assets, files, file_count: files.length, bytes: files.reduce((sum, file) => sum + file.bytes, 0),
    inventory_excludes: ['inventory.json'], verification: 'pending: run doctor and verify with the bundled node from outside the source checkout',
  }
  writeJson(join(output, 'inventory.json'), record)
  console.log(JSON.stringify({ package: output, files: record.file_count, bytes: record.bytes, packages: record.package_instances, browsers: assets.browsers }, null, 2))
  return { output, inventory: record }
}
