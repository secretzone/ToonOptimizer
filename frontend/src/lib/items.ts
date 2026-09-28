import type { Item, ItemSource } from './types'
import { QUALITY_COLORS } from './wow'

export function qualityColor(q: number): string {
  return QUALITY_COLORS[q] ?? QUALITY_COLORS[1]
}

/** Total socket count on an item, including empty ones. `sockets` is additive/optional on
 * `Item`; absent means assume no empty sockets (just what's already gemmed). */
export function socketCount(item: Pick<Item, 'sockets' | 'gem_ids'>): number {
  return item.sockets ?? item.gem_ids?.length ?? 0
}

/** How many of an item's sockets have no gem in them. */
export function emptySocketCount(item: Pick<Item, 'sockets' | 'gem_ids'>): number {
  return Math.max(0, socketCount(item) - (item.gem_ids?.length ?? 0))
}

export function wowheadHref(id: number): string {
  return `https://www.wowhead.com/item=${id}`
}

/** Builds the `data-wowhead` attribute value Wowhead's tooltip script reads, e.g.
 * "item=237631&bonus=10390:1808:226&ilvl=678&gems=213743&ench=7364". Empty parts are omitted. */
export function wowheadDataAttr(item: Pick<Item, 'id' | 'bonus_ids' | 'ilevel' | 'gem_ids' | 'enchant_id'>): string {
  const parts = [`item=${item.id}`]
  if (item.bonus_ids?.length) parts.push(`bonus=${item.bonus_ids.join(':')}`)
  if (item.ilevel) parts.push(`ilvl=${item.ilevel}`)
  if (item.gem_ids?.length) parts.push(`gems=${item.gem_ids.join(':')}`)
  if (item.enchant_id) parts.push(`ench=${item.enchant_id}`)
  return parts.join('&')
}

export function sourceLabel(s: ItemSource | null | undefined): string {
  if (!s) return ''
  switch (s.type) {
    case 'raid': return [s.boss, s.difficulty].filter(Boolean).join(' · ') || s.name
    case 'dungeon': return s.key_level != null ? `${s.name} +${s.key_level}` : s.name
    case 'delve': return [s.name, s.difficulty].filter(Boolean).join(' ')
    case 'vault': return s.boss ? `Vault · ${s.boss}` : 'Great Vault'
    case 'bag': return 'Bags'
    case 'equipped': return 'Equipped'
    default: return s.name
  }
}
