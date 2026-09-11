export default function App() {
  return (
    <div className="min-h-full bg-bg p-8 font-ui text-text">
      <h1 className="text-2xl font-bold">Harbourview</h1>
      <p className="mt-2 text-text3">Scaffold is up.</p>
      <div className="mt-4 flex items-center gap-3">
        <span className="rounded bg-accent px-3 py-2 font-semibold text-accentText">Accent</span>
        <span className="rounded bg-okBg px-3 py-2 text-okText">ok</span>
        <span className="rounded bg-warnBg px-3 py-2 text-warnText">warn</span>
        <span className="rounded bg-dangerBg px-3 py-2 text-dangerText">danger</span>
        <span className="font-mono text-roomNum">412</span>
      </div>
    </div>
  )
}
