/**
 * Fail the release build if a server-only secret reached the browser bundle.
 *
 * The Supabase publishable key is public by design; the *secret* key is not.
 * Two complementary checks run:
 *
 * 1. **Shape** - a real secret key (`sb_secret_…` with a long random body), a
 *    scoped personal access token (`sbp_…`), or a database connection string.
 *    The bare prefixes are ignored because libraries legitimately mention them
 *    in key-format checks and error messages.
 * 2. **Value** - if a server-only variable is present in the build environment,
 *    its exact value must not appear in any emitted asset. This catches a
 *    secret pasted into a `VITE_`-prefixed variable by mistake.
 *
 * Usage: node scripts/check-bundle-secrets.mjs [distDir]
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const distDir = resolve(process.argv[2] ?? 'dist')

const SECRET_SHAPES = [
  { name: 'Supabase secret key', re: /sb_secret_[A-Za-z0-9_-]{20,}/g },
  { name: 'Supabase personal access token', re: /sbp_[A-Za-z0-9]{20,}/g },
  { name: 'PostgreSQL connection string', re: /postgres(?:ql)?:\/\/[^\s"'`]+/g },
]

/** Server-only variables whose *values* must never be shipped. */
const SERVER_ONLY_ENV = [
  'SUPABASE_SECRET_KEY',
  'SUPABASE_SERVICE_ROLE_KEY',
  'SUPABASE_DB_PASSWORD',
  'SUPABASE_DB_URL',
  'SUPABASE_POOLER_URL',
  'SUPABASE_ACCESS_TOKEN',
  'DATABASE_URL',
  'TEST_DATABASE_URL',
  'LOCAL_JWT_SECRET',
]

const FORBIDDEN_VALUES = SERVER_ONLY_ENV.map((name) => ({
  name,
  value: (process.env[name] ?? '').trim(),
})).filter((entry) => entry.value.length >= 16)

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      yield* walk(full)
    } else if (/\.(js|mjs|css|html|map|json|txt)$/.test(entry)) {
      yield full
    }
  }
}

let dist
try {
  dist = statSync(distDir)
} catch {
  console.error(`check-bundle-secrets: ${distDir} does not exist - run vite build first.`)
  process.exit(1)
}
if (!dist.isDirectory()) {
  console.error(`check-bundle-secrets: ${distDir} is not a directory.`)
  process.exit(1)
}

const findings = []
for (const file of walk(distDir)) {
  const contents = readFileSync(file, 'utf8')
  const relative = file.slice(distDir.length + 1)

  for (const { name, re } of SECRET_SHAPES) {
    const matches = contents.match(re)
    // Source maps embed the original sources; report the asset once per shape.
    if (matches) findings.push(`${relative} contains a value shaped like a ${name}`)
  }

  for (const { name, value } of FORBIDDEN_VALUES) {
    if (contents.includes(value)) {
      findings.push(`${relative} contains the value of ${name}`)
    }
  }
}

if (findings.length > 0) {
  console.error('Refusing to ship a bundle that contains server-only secrets:')
  for (const finding of [...new Set(findings)]) console.error(`  - ${finding}`)
  process.exit(1)
}

console.log(`Bundle secret scan passed (${distDir}).`)
