import { LogOut, Moon, Search, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { CommandPalette } from '@/components/layout/command-palette'
import { WorkspaceSwitcher } from '@/components/layout/workspace-switcher'
import { Button } from '@/components/ui/button'
import { useSession } from '@/features/auth/session-provider'

type Theme = 'dark' | 'light'

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (document.documentElement.dataset.theme as Theme) ?? 'dark',
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])
  return [theme, () => setTheme((value) => (value === 'dark' ? 'light' : 'dark'))]
}

export function TopBar() {
  const { user, signOut } = useSession()
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((value) => !value)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-4">
      <WorkspaceSwitcher />

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="ml-2 flex h-8 flex-1 max-w-md items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--background)] px-2.5 text-xs text-[var(--muted-foreground)] hover:border-[var(--border-strong)]"
      >
        <Search className="size-3.5" aria-hidden="true" />
        <span className="flex-1 text-left">Search…</span>
        <kbd className="rounded border border-[var(--border)] px-1 text-[10px]">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? (
            <Sun className="size-4" aria-hidden="true" />
          ) : (
            <Moon className="size-4" aria-hidden="true" />
          )}
        </Button>

        {user ? (
          <div className="flex items-center gap-2 pl-2">
            <div className="hidden text-right sm:block">
              <p className="text-xs font-medium leading-tight text-[var(--foreground)]">
                {user.display_name}
              </p>
              <p className="text-[11px] leading-tight text-[var(--muted-foreground)]">{user.email}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={handleSignOut} aria-label="Sign out">
              <LogOut className="size-4" aria-hidden="true" />
            </Button>
          </div>
        ) : (
          <Button asChild variant="secondary" size="sm">
            <Link to="/login">Sign in</Link>
          </Button>
        )}
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </header>
  )
}
