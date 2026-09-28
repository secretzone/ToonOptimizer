import { useState } from 'react'
import type { Currency } from '../lib/types'
import { iconUrl, QUESTIONMARK_ICON_URL } from '../lib/wow'

type IconStage = 'primary' | 'questionmark' | 'placeholder'

function CurrencyIcon({ icon, size }: { icon: string; size: number }) {
  const [stage, setStage] = useState<IconStage>(icon ? 'primary' : 'placeholder')
  const src = stage === 'primary' ? iconUrl(icon) : stage === 'questionmark' ? QUESTIONMARK_ICON_URL : null
  return (
    <span className="relative inline-block shrink-0 overflow-hidden rounded border border-border-strong bg-bg-soft" style={{ width: size, height: size }}>
      {src ? (
        <img
          src={src}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          draggable={false}
          className="block h-full w-full object-cover"
          onError={() => setStage(stage === 'primary' ? 'questionmark' : 'placeholder')}
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-[8px] font-semibold text-faint">CR</span>
      )}
    </span>
  )
}

/** Icon + amount for the profile's crest currencies (and Catalyst charges, when present). Used
 * both as a compact strip (Import page / CharacterHeader) and, with `showNames`, as the fuller
 * "Your currencies" card on the Upgrades page. Renders nothing when there's nothing to show. */
export function CurrencyStrip({
  currencies, catalystCharges, size = 24, showNames = false, className = '',
}: {
  currencies: Currency[] | undefined
  catalystCharges?: number | null
  size?: number
  showNames?: boolean
  className?: string
}) {
  if (!currencies?.length && catalystCharges == null) return null
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 ${className}`}>
      {currencies?.map((c) => (
        <div key={c.id} className="flex items-center gap-2" title={showNames ? undefined : `${c.name}: ${c.amount.toLocaleString()}`}>
          <CurrencyIcon icon={c.icon} size={size} />
          {showNames ? (
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{c.name}</div>
              <div className="text-xs tabular-nums text-muted">
                {c.amount.toLocaleString()}{c.max_quantity != null ? ` / ${c.max_quantity.toLocaleString()}` : ''}
              </div>
            </div>
          ) : (
            <span className="text-sm tabular-nums">{c.amount.toLocaleString()}</span>
          )}
        </div>
      ))}
      {catalystCharges != null && (
        <div className="flex items-center gap-2" title={showNames ? undefined : `Catalyst charges: ${catalystCharges}`}>
          <span
            className="flex items-center justify-center rounded border border-border-strong bg-bg-soft text-[9px] font-semibold text-faint"
            style={{ width: size, height: size }}
          >
            CT
          </span>
          {showNames ? (
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">Catalyst charges</div>
              <div className="text-xs tabular-nums text-muted">{catalystCharges}</div>
            </div>
          ) : (
            <span className="text-sm tabular-nums">{catalystCharges}</span>
          )}
        </div>
      )}
    </div>
  )
}
