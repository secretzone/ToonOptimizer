import type { DecodedTalents, TalentTrees } from './types'

/** Normalize the loosely specified decode response into node_id -> rank. */
export function normalizeDecoded(d: DecodedTalents): Map<number, number> {
  const out = new Map<number, number>()
  const sel = d.selected
  if (Array.isArray(sel)) {
    for (const entry of sel) {
      if (entry && typeof entry === 'object' && 'node_id' in entry && 'rank' in entry) {
        out.set(Number((entry as { node_id: number }).node_id), Number((entry as { rank: number }).rank))
      } else if (entry && typeof entry === 'object') {
        for (const [k, v] of Object.entries(entry)) out.set(Number(k), Number(v))
      }
    }
  } else if (sel && typeof sel === 'object') {
    for (const [k, v] of Object.entries(sel)) out.set(Number(k), Number(v))
  }
  return out
}

export type TalentDiff = {
  added: { id: number; rank: number }[]
  removed: { id: number; rank: number }[]
  changed: { id: number; from: number; to: number }[]
}

export function diffTalents(a: Map<number, number>, b: Map<number, number>): TalentDiff {
  const diff: TalentDiff = { added: [], removed: [], changed: [] }
  for (const [id, rank] of b) {
    const prev = a.get(id)
    if (prev === undefined) diff.added.push({ id, rank })
    else if (prev !== rank) diff.changed.push({ id, from: prev, to: rank })
  }
  for (const [id, rank] of a) if (!b.has(id)) diff.removed.push({ id, rank })
  return diff
}

export function nodeNameLookup(trees: TalentTrees | null): (id: number) => string {
  const names = new Map<number, string>()
  if (trees) {
    for (const list of [trees.class_tree, trees.spec_tree]) {
      for (const n of list ?? []) {
        if (n && typeof n.id === 'number' && typeof n.name === 'string') names.set(n.id, n.name)
      }
    }
  }
  return (id) => names.get(id) ?? `Node ${id}`
}
