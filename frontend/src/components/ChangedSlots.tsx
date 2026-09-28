import { ArrowRight } from 'lucide-react'
import type { CharacterProfile, Item, ResultRow } from '../lib/types'
import { SLOT_LABELS } from '../lib/wow'
import { useWowheadRefresh } from '../lib/wowhead'
import { ItemCard, EmptySlot } from './ItemCard'

/** Shows each changed slot as current -> new item. */
export function ChangedSlots({ row, profile }: { row: ResultRow; profile: CharacterProfile | null }) {
  useWowheadRefresh([row])
  const changes = row.meta.changes ?? (row.meta.item ? { [row.meta.item.slot]: row.meta.item } : null)
  if (!changes || !Object.keys(changes).length) {
    if (row.meta.items?.length) {
      return (
        <div className="flex flex-col gap-1">
          {row.meta.items.map((it: Item) => <ItemCard key={it.key} item={it} slotLabel={SLOT_LABELS[it.slot]} showSource />)}
        </div>
      )
    }
    return <div className="text-sm text-muted">No item changes recorded for this row.</div>
  }
  return (
    <div className="flex flex-col gap-2">
      {Object.entries(changes).map(([slot, item]) => {
        const current = profile?.equipped[slot]
        return (
          <div key={slot} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-md border border-border bg-bg-soft/50 p-1.5">
            <div>
              <div className="label mb-1 px-2">{SLOT_LABELS[slot] ?? slot} · current</div>
              {current ? <ItemCard item={current} compact dim /> : <EmptySlot label={SLOT_LABELS[slot] ?? slot} />}
            </div>
            <ArrowRight size={16} className="text-accent" />
            <div>
              <div className="label mb-1 px-2">new{item.ilevel !== current?.ilevel && current ? ` (${item.ilevel > current.ilevel ? '+' : ''}${item.ilevel - current.ilevel} ilvl)` : ''}</div>
              <ItemCard item={item} compact showSource />
            </div>
          </div>
        )
      })}
    </div>
  )
}
