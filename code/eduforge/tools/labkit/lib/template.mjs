/** 读取实验模板：目录按 manifest 的 template_id 查找，不靠目录名猜。 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

function collectManifests(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    if (entry.isDirectory()) collectManifests(p, out)
    else if (entry.name === 'manifest.yaml') out.push(p)
  }
}

export function findTemplateDir(repoRoot, templateId) {
  const base = join(repoRoot, 'code', 'eduforge', 'catalog', 'templates')
  const manifests = []
  collectManifests(base, manifests)
  for (const manifest of manifests) {
    const text = readFileSync(manifest, 'utf8')
    const m = text.match(/^template_id:\s*(.+)$/m)
    if (m && m[1].trim() === templateId) return dirname(manifest)
  }
  const err = new Error(`TEMPLATE_NOT_FOUND: ${templateId}`)
  err.code = 'TEMPLATE_NOT_FOUND'
  throw err
}

export function loadTemplate(repoRoot, templateId = 'mechanics.projectile') {
  const dir = findTemplateDir(repoRoot, templateId)
  const recipesPath = join(dir, 'recipes.json')
  const recipes = JSON.parse(readFileSync(recipesPath, 'utf8'))
  if (recipes.template_id !== templateId) {
    const err = new Error(`TEMPLATE_ID_MISMATCH: ${recipes.template_id} != ${templateId}`)
    err.code = 'TEMPLATE_ID_MISMATCH'
    throw err
  }
  return { dir, recipesPath, ...recipes }
}

export function getRecipe(template, recipeId) {
  const recipe = template.recipes.find(r => r.id === recipeId)
  if (!recipe) {
    const err = new Error(`RECIPE_UNKNOWN: ${recipeId}`)
    err.code = 'RECIPE_UNKNOWN'
    throw err
  }
  return recipe
}
