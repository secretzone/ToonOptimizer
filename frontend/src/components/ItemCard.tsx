import { useState, type ReactNode, type MouseEvent } from 'react'
import { createPortal } from 'react-dom'
import type { Item, ItemSource } from '../lib/types'
import { QUALITY_NAMES, SLOT_LABELS, STAT_LABELS, iconUrl, slotAbbr, titleCase, QUESTIONMARK_ICON_URL } from '../lib/wow'
import { emptySocketCount, qualityColor, sourceLabel, wowheadDataAttr, wowheadHref } from '../lib/items'
import { useWowheadActive } from '../lib/wowhead'
import { useStore } from '../store'

export function SourceChip({ source, className = '' }: { source: ItemSource | null | undefined; className?: string }) {
  if (!source) return null
  const colors: Record<string, string> = {
    raid: 'text-orange-300 border-orange-900/60', dungeon: 'text-sky-300 border-sky-900/60', world_boss: 'text-lime-300 border-lime-900/60',
    delve: 'text-violet-300 border-violet-900/60', crafted: 'text-amber-200 border-amber-900/60', vault: 'text-fuchsia-300 border-fuchsia-900/60',
    bag: 'text-muted', equipped: 'text-muted',
  }
  return <span className={`chip ${colors[source.type] ?? ''} ${className}`} title={source.name}>{sourceLabel(source)}</span>
}

type IconStage = 'primary' | 'questionmark' | 'placeholder'

export function ItemIcon({ item, size = 40, className = '' }: { item: Pick<Item, 'icon' | 'quality' | 'name' | 'slot' | 'resolved'>; size?: number; className?: string }) {
  const wowheadEnabled = useStore((s) => s.wowheadTooltips)
  const unresolved = item.resolved === false
  const [stage, setStage] = useState<IconStage>(!unresolved && item.icon ? 'primary' : 'placeholder')
  const src = stage === 'primary' ? iconUrl(item.icon) : stage === 'questionmark' ? QUESTIONMARK_ICON_URL : null
  const handleError = () => {
    // Only bother with Wowhead's own question-mark art if its tooltip script is in play;
    // otherwise go straight to our slot placeholder.
    if (stage === 'primary' && wowheadEnabled) setStage('questionmark')
    else setStage('placeholder')
  }
  return (
    <span className={`relative inline-block shrink-0 overflow-hidden rounded border-2 bg-bg-soft ${className}`} style={{ width: size, height: size, borderColor: qualityColor(item.quality) }}>
      {src ? (
        <img src={src} alt="" width={size} height={size} loading="lazy" onError={handleError} className="block h-full w-full object-cover" draggable={false} />
      ) : (
        <span className="flex h-full w-full items-center justify-center font-semibold leading-none text-faint" style={{ fontSize: size <= 26 ? 8 : 10 }}>
          {slotAbbr(item.slot)}
        </span>
      )}
    </span>
  )
}

/** Wraps icon/name content in a Wowhead-tooltip anchor (data-wowhead, active) or, when Wowhead
 * tooltips are off/unavailable/the item is unresolved, in our own hover Tooltip + ItemTooltip. */
export function WowheadOrFallback({ item, active, className = '', children }: { item: Item; active: boolean; className?: string; children: ReactNode }) {
  const anchor = (
    <a
      href={wowheadHref(item.id)}
      {...(active ? { 'data-wowhead': wowheadDataAttr(item) } : {})}
      target="_blank"
      rel="noreferrer"
      className={`contents ${className}`}
    >
      {children}
    </a>
  )
  if (active) return anchor
  return <Tooltip content={<ItemTooltip item={item} />}>{anchor}</Tooltip>
}

/** Hover tooltip anchored to the cursor, rendered in a portal so it isn't clipped. */
export function Tooltip({ content, children, className = '' }: { content: ReactNode; children: ReactNode; className?: string }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const move = (e: MouseEvent) => {
    const w = 300
    const x = Math.min(e.clientX + 16, window.innerWidth - w - 8)
    const y = Math.min(e.clientY + 12, window.innerHeight - 8)
    setPos({ x, y })
  }
  return (
    <span className={`inline-block ${className}`} onMouseEnter={move} onMouseMove={move} onMouseLeave={() => setPos(null)}>
      {children}
      {pos &&
        createPortal(
          <div className="pointer-events-none fixed z-[100] w-[300px] -translate-y-full" style={{ left: pos.x, top: pos.y, transform: pos.y > window.innerHeight / 2 ? 'translateY(-100%)' : undefined }}>
            {content}
          </div>,
          document.body,
        )}
    </span>
  )
}

export function ItemTooltip({ item }: { item: Item }) {
  const unresolved = item.resolved === false
  const displayName = unresolved ? `Item ${item.id}` : item.name
  const stats = Object.entries(item.stats ?? {})
  const primary = stats.filter(([k]) => ['strength', 'agility', 'intellect', 'stamina', 'armor', 'weapon_dps'].includes(k))
  const secondary = stats.filter(([k]) => !['strength', 'agility', 'intellect', 'stamina', 'armor', 'weapon_dps'].includes(k))
  if (unresolved) {
    return (
      <div className="rounded-lg border border-border-strong bg-[#0b0d11]/98 p-3 text-xs shadow-2xl">
        <div className="flex items-start gap-2">
          <ItemIcon item={item} size={36} />
          <div className="min-w-0">
            <div className="text-sm font-semibold leading-tight text-text">{displayName}</div>
            <div className="mt-0.5"><span className="chip text-amber-300 border-amber-700/60">unresolved</span></div>
          </div>
        </div>
        <div className="mt-2 text-muted">This item could not be looked up against the cached game data. Refresh data in Settings, then re-import.</div>
        <div className="mono mt-1.5 text-[10px] text-faint">id {item.id}</div>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-border-strong bg-[#0b0d11]/98 p-3 text-xs shadow-2xl">
      <div className="flex items-start gap-2">
        <ItemIcon item={item} size={36} />
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-tight" style={{ color: qualityColor(item.quality) }}>{displayName}</div>
          <div className="text-muted">{QUALITY_NAMES[item.quality] ?? ''} · Item Level <span className="text-accent">{item.ilevel}</span></div>
        </div>
      </div>
      <div className="mt-2 flex justify-between text-muted">
        <span>{SLOT_LABELS[item.slot] ?? titleCase(item.slot)}</span>
        {item.set_id != null && <span className="text-good">Set piece</span>}
      </div>
      {primary.length > 0 && (
        <ul className="mt-1.5">
          {primary.map(([k, v]) => (
            <li key={k} className="text-text">+{Math.round(v).toLocaleString()} {STAT_LABELS[k] ?? titleCase(k)}</li>
          ))}
        </ul>
      )}
      {secondary.length > 0 && (
        <ul className="mt-1">
          {secondary.map(([k, v]) => (
            <li key={k} className="text-good">+{Math.round(v).toLocaleString()} {STAT_LABELS[k] ?? titleCase(k)}</li>
          ))}
        </ul>
      )}
      {(item.gem_ids?.length > 0 || emptySocketCount(item) > 0 || item.enchant_id || item.crafting_quality) && (
        <ul className="mt-1.5 text-muted">
          {item.gem_ids?.map((g, i) => <li key={i} className="text-info">Gem: {g}</li>)}
          {Array.from({ length: emptySocketCount(item) }).map((_, i) => <li key={`empty-${i}`} className="text-faint">Empty socket</li>)}
          {item.enchant_id ? <li className="text-good">Enchant: {item.enchant_id}</li> : null}
          {item.crafting_quality ? <li className="text-accent">Crafted quality {item.crafting_quality}{item.crafted_stats?.length ? ` · stats ${item.crafted_stats.join('/')}` : ''}</li> : null}
        </ul>
      )}
      {item.unique_equipped && <div className="mt-1 text-muted">{item.unique_equipped}</div>}
      {item.source && <div className="mt-1.5 text-muted">Source: {sourceLabel(item.source)}{item.source.type === 'raid' ? ` (${item.source.name})` : ''}</div>}
      <div className="mono mt-1.5 text-[10px] text-faint">id {item.id}{item.bonus_ids?.length ? ` · bonus ${item.bonus_ids.join('/')}` : ''}</div>
    </div>
  )
}

export function ItemCard({
  item, slotLabel, compact = false, showSource = false, right, className = '', onClick, selected, dim,
}: {
  item: Item; slotLabel?: string; compact?: boolean; showSource?: boolean; right?: ReactNode; className?: string
  onClick?: () => void; selected?: boolean; dim?: boolean
}) {
  const active = useWowheadActive(item)
  const unresolved = item.resolved === false
  const displayName = unresolved ? `Item ${item.id}` : item.name
  const chips: ReactNode[] = []
  if (unresolved) chips.push(<span key="unresolved" className="chip text-amber-300 border-amber-700/60">unresolved</span>)
  if (item.gem_ids?.length) chips.push(<span key="gem" className="chip text-info">{item.gem_ids.length} gem{item.gem_ids.length > 1 ? 's' : ''}</span>)
  const emptySockets = emptySocketCount(item)
  if (emptySockets > 0) chips.push(<span key="emptysocket" className="chip border-dashed text-faint">{emptySockets} empty socket{emptySockets > 1 ? 's' : ''}</span>)
  if (item.enchant_id) chips.push(<span key="ench" className="chip text-good">enchanted</span>)
  if (item.set_id != null) chips.push(<span key="set" className="chip text-accent">tier</span>)
  if (item.crafting_quality) chips.push(<span key="craft" className="chip">Q{item.crafting_quality}</span>)
  const body = (
    <div
      className={`flex min-w-0 items-center gap-2.5 rounded-md border px-2 py-1.5 transition-colors ${selected ? 'border-accent bg-accent/10' : 'border-transparent'} ${onClick ? 'cursor-pointer hover:bg-surface-2' : ''} ${dim ? 'opacity-50' : ''} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
    >
      <WowheadOrFallback item={item} active={active}>
        <ItemIcon item={item} size={compact ? 30 : 40} />
      </WowheadOrFallback>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <WowheadOrFallback item={item} active={active} className="min-w-0 truncate">
            <span className="truncate text-sm font-medium" style={{ color: qualityColor(item.quality) }} title={displayName}>{displayName}</span>
          </WowheadOrFallback>
          <span className="shrink-0 text-xs tabular-nums text-accent">{item.ilevel}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1 text-xs text-muted">
          {slotLabel && <span>{slotLabel}</span>}
          {!compact && chips}
          {showSource && item.source && <SourceChip source={item.source} />}
        </div>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  )
  return body
}

export function EmptySlot({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-dashed border-border px-2 py-1.5 opacity-60">
      <span className="inline-block h-10 w-10 shrink-0 rounded border-2 border-border bg-bg-soft" />
      <div className="text-sm text-faint">{label} — empty</div>
    </div>
  )
}
