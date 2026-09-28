// Small helpers shared between lib/mock.ts and lib/mockCharacters.ts (Characters/Advisor/Reports
// fixtures). Split out so mockCharacters.ts doesn't need a circular import on mock.ts (mock.ts
// imports fixtures *from* mockCharacters.ts, not the other way around).
import type { Item, ItemSource } from './types'

// ---------- deterministic prng ----------
export function rng(seed: number) {
  let s = seed >>> 0 || 1
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}
export function hash(str: string): number {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619)
  return h >>> 0
}
export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ---------- items ----------
export type ItemSeed = {
  id: number; name: string; slot: string; inv: number; ilevel: number; icon: string
  quality?: number; gems?: number[]; enchant?: number | null; set?: number | null; unique?: string | null
  crafted?: [number[], number]; bonus?: number[]
  /** Total sockets, including empty ones. Defaults to `gems?.length` (no empty sockets). */
  sockets?: number
}

export function mkItem(key: string, seed: ItemSeed, source: ItemSource, sec: [string, string], stats?: Record<string, number>): Item {
  const bonus = seed.bonus ?? [seed.ilevel > 660 ? 10390 : 10353, 1808, Math.round(seed.ilevel / 3)]
  const parts = [`${seed.slot}=`, `id=${seed.id}`, `bonus_id=${bonus.join('/')}`, `ilevel=${seed.ilevel}`]
  if (seed.gems?.length) parts.push(`gem_id=${seed.gems.join('/')}`)
  if (seed.enchant) parts.push(`enchant_id=${seed.enchant}`)
  if (seed.crafted) parts.push(`crafted_stats=${seed.crafted[0].join('/')}`, `crafting_quality=${seed.crafted[1]}`)
  return {
    key,
    id: seed.id,
    name: seed.name,
    slot: seed.slot,
    inventory_type: seed.inv,
    ilevel: seed.ilevel,
    quality: seed.quality ?? 4,
    icon: seed.icon,
    bonus_ids: bonus,
    gem_ids: seed.gems ?? [],
    sockets: seed.sockets ?? (seed.gems?.length ?? 0),
    enchant_id: seed.enchant ?? null,
    crafted_stats: seed.crafted?.[0] ?? [],
    crafting_quality: seed.crafted?.[1] ?? null,
    unique_equipped: seed.unique ?? null,
    set_id: seed.set ?? null,
    stats: stats ?? plateStats(seed.slot, seed.ilevel, sec),
    source,
    simc_string: parts.join(','),
  }
}

/** Generic plate/strength-class secondary-stat curve (used by the Frost DK fixture). */
export function plateStats(slot: string, ilevel: number, sec: [string, string]): Record<string, number> {
  const mult: Record<string, number> = {
    head: 1, chest: 1, legs: 1, shoulder: 0.75, hands: 0.75, feet: 0.75, waist: 0.75,
    wrist: 0.56, back: 0.56, neck: 0.56, finger1: 0.56, finger2: 0.56, finger: 0.56,
    trinket1: 0.56, trinket2: 0.56, trinket: 0.56, main_hand: 0.6, off_hand: 0.6,
  }
  const m = mult[slot] ?? 0.75
  const base = Math.round(Math.pow(1.055, ilevel - 600) * 1000)
  const stats: Record<string, number> = {}
  const jewelry = ['neck', 'finger', 'finger1', 'finger2'].includes(slot)
  const trinket = slot.startsWith('trinket')
  if (!jewelry && !trinket) {
    stats.strength = Math.round(base * 1.7 * m)
    stats.stamina = Math.round(base * 3.6 * m)
    stats.armor = Math.round(base * 0.9 * m)
  } else if (trinket) {
    stats.strength = Math.round(base * 1.9 * m)
  } else {
    stats.stamina = Math.round(base * 3.6 * m)
  }
  if (!trinket) {
    stats[sec[0]] = Math.round(base * (jewelry ? 1.9 : 1.05) * m)
    stats[sec[1]] = Math.round(base * (jewelry ? 1.25 : 0.7) * m)
  }
  if (slot === 'main_hand' || slot === 'off_hand') stats.weapon_dps = Math.round(Math.pow(1.055, ilevel - 600) * 620)
  return stats
}

/** Agility-class secondary-stat curve (used by the Marksmanship Hunter fixture) — same shape as
 * `plateStats` but with an agility primary and no armor line (leather/mail flavor, doesn't matter
 * for the mock's DPS math). */
export function leatherStats(slot: string, ilevel: number, sec: [string, string]): Record<string, number> {
  const mult: Record<string, number> = {
    head: 1, chest: 1, legs: 1, shoulder: 0.75, hands: 0.75, feet: 0.75, waist: 0.75,
    wrist: 0.56, back: 0.56, neck: 0.56, finger1: 0.56, finger2: 0.56, finger: 0.56,
    trinket1: 0.56, trinket2: 0.56, trinket: 0.56, main_hand: 0.9, off_hand: 0.6,
  }
  const m = mult[slot] ?? 0.75
  const base = Math.round(Math.pow(1.055, ilevel - 600) * 1000)
  const stats: Record<string, number> = {}
  const jewelry = ['neck', 'finger', 'finger1', 'finger2'].includes(slot)
  const trinket = slot.startsWith('trinket')
  if (!jewelry && !trinket) {
    stats.agility = Math.round(base * 1.7 * m)
    stats.stamina = Math.round(base * 3.0 * m)
  } else if (trinket) {
    stats.agility = Math.round(base * 1.9 * m)
  } else {
    stats.stamina = Math.round(base * 3.0 * m)
  }
  if (!trinket) {
    stats[sec[0]] = Math.round(base * (jewelry ? 1.9 : 1.05) * m)
    stats[sec[1]] = Math.round(base * (jewelry ? 1.25 : 0.7) * m)
  }
  if (slot === 'main_hand') stats.weapon_dps = Math.round(Math.pow(1.055, ilevel - 600) * 540)
  return stats
}
