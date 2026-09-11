import { useAssets } from '../../api/hooks/content'
import type { AssetOut } from '../../api/types'
import { Dropdown } from '../../components/ui'

export function AssetPicker({ onPick }: { onPick: (asset: AssetOut) => void }) {
  const { data: assets } = useAssets()
  const available = (assets ?? []).filter((a) => a.active)

  return (
    <Dropdown label="Attach">
      {(close) =>
        available.length === 0 ? (
          <p className="px-3 py-2 text-xs text-text3">No assets</p>
        ) : (
          <>
            {available.map((asset) => (
              <button
                key={asset.id}
                role="menuitem"
                className="flex w-full flex-col items-start px-3 py-2 text-left hover:bg-surface2"
                onClick={() => {
                  close()
                  onPick(asset)
                }}
              >
                <span className="text-[13px] font-semibold">{asset.name}</span>
                <span className="font-mono text-xs text-text3">/a/{asset.shortCode}</span>
              </button>
            ))}
          </>
        )
      }
    </Dropdown>
  )
}
