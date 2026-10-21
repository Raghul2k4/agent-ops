/**
 * Supabase client for the browser.
 *
 * Only the **publishable** key is ever read here: it is public by design and is
 * protected by Row Level Security. The secret key must never be shipped to the
 * browser, and `scripts/check-bundle-secrets.mjs` fails the build if it is.
 *
 * The client is `null` when the project is not configured, so the UI can show an
 * explicit setup message instead of crashing at import time.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.trim()
const publishableKey = (
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined
)?.trim()

export const isSupabaseConfigured = Boolean(url && publishableKey)

export const supabaseUrl = url ?? null

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url as string, publishableKey as string, {
      auth: {
        // The access token is persisted and refreshed by the SDK. It is sent to
        // the AgentOps API as `Authorization: Bearer`; no cookie is involved.
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: 'pkce',
      },
    })
  : null

export function assertSupabaseClient(): SupabaseClient {
  if (!supabase) {
    throw new Error(
      'Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in apps/web/.env.',
    )
  }
  return supabase
}
