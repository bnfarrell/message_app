import { useState } from 'react'
import { importReport, useImportUnits } from '../../api/hooks/pm'
import { Button, Dialog, useToast } from '../../components/ui'

const COLUMNS = 'code,kind,name,floor,room_type,external_id'

/** Upload a CSV of units. A rejection lists every bad row in place — nothing was written, so
 *  the admin fixes the file and tries again without leaving the dialog (PM spec §7.6). */
export function ImportUnitsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const importUnits = useImportUnits()
  const toast = useToast()
  const report = importReport(importUnits.error)

  function close() {
    importUnits.reset()
    setFile(null)
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Import units from CSV"
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!file}
            loading={importUnits.isPending}
            onClick={() => {
              if (!file) return
              importUnits.mutate(file, {
                onSuccess: (result) => {
                  toast(`Imported: ${result.created} created, ${result.updated} updated`)
                  close()
                },
              })
            }}
          >
            Import
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-xs text-text3">
          Header row required, exactly: <code className="font-mono">{COLUMNS}</code>. <code className="font-mono">kind</code> is
          one of guest_room, common_area, equipment. Rows with a code that already exists are updated.
          A sample lives at <code className="font-mono">fixtures/maintainable_units.sample.csv</code>.
        </p>
        <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="units-csv">
          CSV file
        </label>
        <input
          id="units-csv"
          type="file"
          accept=".csv,text/csv"
          className="text-sm"
          onChange={(event) => {
            importUnits.reset()
            setFile(event.target.files?.[0] ?? null)
          }}
        />
        {report ? (
          <div role="alert" className="rounded border border-danger bg-dangerBg p-3 text-xs text-dangerText">
            <p className="mb-2 font-semibold">Nothing was imported. Fix these rows and try again:</p>
            <table className="w-full">
              <tbody>
                {(report.errors ?? []).map((e, i) => (
                  <tr key={i}>
                    <td className="pr-3 font-mono">Line {e.line}</td>
                    <td className="pr-3 font-mono">{e.field}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : importUnits.error ? (
          <p role="alert" className="text-xs text-dangerText">{importUnits.error.message}</p>
        ) : null}
      </div>
    </Dialog>
  )
}
