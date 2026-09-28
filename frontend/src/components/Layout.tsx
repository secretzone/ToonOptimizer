import { NavLink, Outlet, useLocation } from 'react-router'
import {
  Upload, Zap, Trophy, Gem, Scale, Shirt, GitBranch, Terminal, History, Settings, Activity, ArrowUpCircle, Sparkles,
  FlaskConical, FileText,
} from 'lucide-react'
import { useStore } from '../store'
import { CharacterHeader } from './CharacterHeader'
import { CharacterSwitcher } from './CharacterSwitcher'
import { ToastHost } from './Toast'
import { ErrorBoundary } from './ErrorBoundary'
import { MockBanner } from './MockBanner'
import { isTerminal, MOCK } from '../lib/api'
import type { PageKey } from '../store'

const NAV: { to: string; label: string; icon: typeof Upload; page?: PageKey; end?: boolean }[] = [
  { to: '/', label: 'Import', icon: Upload, end: true },
  { to: '/quick', label: 'Quick Sim', icon: Zap, page: 'quick' },
  { to: '/topgear', label: 'Top Gear', icon: Trophy, page: 'topgear' },
  { to: '/droptimizer', label: 'Droptimizer', icon: Gem, page: 'droptimizer' },
  { to: '/upgrades', label: 'Upgrades', icon: ArrowUpCircle, page: 'upgrades' },
  { to: '/gems', label: 'Gems & Enchants', icon: Sparkles, page: 'gems' },
  { to: '/consumables', label: 'Consumables', icon: FlaskConical, page: 'consumables' },
  { to: '/statweights', label: 'Stat Weights', icon: Scale, page: 'statweights' },
  { to: '/gearcompare', label: 'Gear Compare', icon: Shirt, page: 'gearcompare' },
  { to: '/talentcompare', label: 'Talent Compare', icon: GitBranch, page: 'talentcompare' },
  { to: '/advanced', label: 'Advanced', icon: Terminal, page: 'advanced' },
  { to: '/history', label: 'History', icon: History },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Layout() {
  const profile = useStore((s) => s.profile)
  const pages = useStore((s) => s.pages)
  const location = useLocation()
  return (
    <div className="flex h-full flex-col">
      <MockBanner />
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-bg-soft">
          <div className="flex items-center gap-2 px-4 py-4">
            <Activity size={20} className="text-accent" />
            <span className="text-base font-bold tracking-tight">ToonOptimizer</span>
            {MOCK && <span className="chip ml-auto text-accent">mock</span>}
          </div>
          <div className="flex flex-col gap-2.5 border-y border-border px-4 py-3">
            <CharacterSwitcher />
            {profile ? <CharacterHeader profile={profile} compact /> : <div className="text-xs text-faint">No character loaded</div>}
          </div>
          <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Main">
            {NAV.map(({ to, label, icon: Icon, page, end }) => {
              const job = page ? pages[page].job : null
              const running = job && !isTerminal(job)
              const hasResult = page ? !!pages[page].result : false
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) => `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${isActive ? 'bg-surface-2 text-text' : 'text-muted hover:bg-surface hover:text-text'}`}
                >
                  <Icon size={16} />
                  <span className="flex-1">{label}</span>
                  {running && <span className="h-2 w-2 animate-pulse rounded-full bg-accent" title="Running" />}
                  {!running && hasResult && <span className="h-1.5 w-1.5 rounded-full bg-good/70" title="Result ready" />}
                </NavLink>
              )
            })}
          </nav>
          <div className="px-4 py-3 text-[10px] text-faint">Local SimulationCraft runner</div>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] p-5">
            <ErrorBoundary key={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
      <ToastHost />
    </div>
  )
}
