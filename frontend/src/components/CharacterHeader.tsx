import type { CharacterProfile } from '../lib/types'
import { CLASS_COLORS, averageIlvl, titleCase } from '../lib/wow'
import { fmtDate } from '../lib/format'
import { CurrencyStrip } from './CurrencyStrip'

export function CharacterHeader({ profile, compact = false }: { profile: CharacterProfile; compact?: boolean }) {
  const color = CLASS_COLORS[profile.klass] ?? '#fff'
  const ilvl = averageIlvl(profile.equipped)
  if (compact) {
    return (
      <div className="flex items-center gap-2.5">
        <span className="h-8 w-1 rounded-full" style={{ background: color }} />
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" style={{ color }}>{profile.name}</div>
          <div className="truncate text-[11px] text-muted">{titleCase(profile.spec)} {titleCase(profile.klass)} · {ilvl.toFixed(1)}</div>
        </div>
      </div>
    )
  }
  return (
    <div className="card flex flex-col gap-3 p-4" style={{ borderLeft: `4px solid ${color}` }}>
      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border-2 text-xl font-bold" style={{ borderColor: color, color }}>
          {profile.name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="text-xl font-semibold" style={{ color }}>{profile.name}</h2>
            <span className="text-sm text-muted">{profile.realm ? `${profile.realm} (${profile.region.toUpperCase()})` : profile.region.toUpperCase()}</span>
          </div>
          <div className="text-sm text-muted">
            Level {profile.level} {titleCase(profile.race)} <span style={{ color }}>{titleCase(profile.spec)} {titleCase(profile.klass)}</span>
            {Object.keys(profile.professions ?? {}).length > 0 && (
              <span> · {Object.entries(profile.professions).map(([k, v]) => `${titleCase(k)} ${v}`).join(', ')}</span>
            )}
          </div>
        </div>
        <div className="flex gap-6 text-right">
          <div>
            <div className="label">Item level</div>
            <div className="text-2xl font-semibold tabular-nums text-accent">{ilvl.toFixed(1)}</div>
          </div>
          <div className="hidden sm:block">
            <div className="label">Imported</div>
            <div className="text-sm text-muted">{fmtDate(profile.imported_at)}</div>
          </div>
        </div>
      </div>
      <CurrencyStrip currencies={profile.currencies} catalystCharges={profile.catalyst_charges} className="border-t border-border pt-3" />
    </div>
  )
}
