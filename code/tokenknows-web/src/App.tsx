function App() {
  return (
    <div className="bg-bg-page min-h-screen p-8 font-ui">
      <div className="bg-bg-card border border-border-subtle rounded-lg p-6 max-w-2xl shadow-elev-1">
        <h1 className="font-content text-h1 text-text-primary">TokenKnows · Bootstrap OK</h1>
        <p className="text-body text-text-muted mt-2">
          看到对的颜色 + serif 字体的标题 + Poppins 正文,token 链路就通了。
        </p>
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <button className="bg-accent-primary text-inverse-text px-4 py-2 rounded-md text-body-sm font-medium">
            主 CTA (陶土橙)
          </button>
          <span className="bg-success-bg text-success-dark px-2 py-0.5 rounded text-micro font-medium">
            success
          </span>
          <span className="bg-warning-bg text-warning px-2 py-0.5 rounded text-micro font-medium">
            warning
          </span>
          <span className="bg-danger-bg text-danger px-2 py-0.5 rounded text-micro font-medium">
            danger
          </span>
        </div>
        <p className="text-caption text-text-subtle mt-4 font-mono">
          下一步 → cat docs/engineering_handoff/tasks/T01-auth.md
        </p>
      </div>
    </div>
  )
}
export default App
