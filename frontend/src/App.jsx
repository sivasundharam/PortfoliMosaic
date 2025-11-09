import React, { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

function createSessionName(idx) {
  return `Session ${idx}`
}

export default function App() {
  const [busy, setBusy] = useState(false)
  const [sessions, setSessions] = useState(() => [{ id: crypto.randomUUID(), name: createSessionName(1), documents: [], messages: [] }])
  const [activeSessionId, setActiveSessionId] = useState(() => sessions[0].id)
  const [questionInput, setQuestionInput] = useState('What are my holdings?')
  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const uploadProgressRef = useRef({})

  const active = useMemo(() => sessions.find(s => s.id === activeSessionId) || sessions[0], [sessions, activeSessionId])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [active.messages])

  function addSession() {
    const idx = sessions.length + 1
    const s = { id: crypto.randomUUID(), name: createSessionName(idx), documents: [], messages: [] }
    setSessions(prev => [...prev, s])
    setActiveSessionId(s.id)
  }

  function deleteSession(id) {
    setSessions(prev => {
      const filtered = prev.filter(s => s.id !== id)
      const next = filtered.length ? filtered : [{ id: crypto.randomUUID(), name: createSessionName(1), documents: [], messages: [] }]
      if (!filtered.find(s => s.id === activeSessionId)) {
        setActiveSessionId(next[0].id)
      }
      return next
    })
  }

  function renameSession(id, name) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, name } : s))
  }

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function uploadFile(file) {
    const tempId = crypto.randomUUID()
    const tempDoc = { id: tempId, filename: file.name, type: null, status: 'uploading' }

    // Add temp doc immediately
    setSessions(prev => prev.map(s => s.id === active.id ? { ...s, documents: [...s.documents, tempDoc] } : s))
    uploadProgressRef.current[tempId] = { status: 'uploading', progress: 0 }

    try {
      const form = new FormData()
      form.append('file', file)
      form.append('session_id', active.id)  // Include session_id
      const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error('Upload failed')
      const data = await res.json()
      
      const doc = { id: data.document_id, filename: data.filename || file.name, type: data.document_type || null, status: data.extraction_status || 'processing' }
      
      // Replace temp doc with real one
      setSessions(prev => prev.map(s => s.id === active.id ? {
        ...s,
        documents: s.documents.map(d => d.id === tempId ? doc : d)
      } : s))
      
      uploadProgressRef.current[data.document_id] = { status: data.extraction_status, progress: 50 }
      
      // Poll for status updates
      pollDocumentStatus(data.document_id)
    } catch (err) {
      setSessions(prev => prev.map(s => s.id === active.id ? {
        ...s,
        documents: s.documents.filter(d => d.id !== tempId)
      } : s))
      delete uploadProgressRef.current[tempId]
    }
  }

  function pollDocumentStatus(documentId) {
    let attempts = 0
    const maxAttempts = 60  // 60 attempts with dynamic intervals = ~160s coverage

    const poll = async () => {
      if (attempts >= maxAttempts) {
        console.log(`⏹️ Polling stopped for ${documentId} - max attempts reached`)
        return
      }
      attempts++

      try {
        const res = await fetch(`${API}/documents/${encodeURIComponent(documentId)}/status`)
        if (!res.ok) {
          console.log(`⚠️ Poll attempt ${attempts} failed for ${documentId}`)
          // Use dynamic interval even for retries
          const retryInterval = attempts < 5 ? 1000 : attempts < 15 ? 2000 : 3000
          setTimeout(poll, retryInterval)
          return
        }
        const status = await res.json()

        console.log(`📊 Poll attempt ${attempts} for ${documentId}: status=${status.extraction_status}`)

        uploadProgressRef.current[documentId] = {
          status: status.extraction_status,
          progress: status.extraction_status === 'completed' ? 100 : status.extraction_status === 'extracting' ? 75 : 50
        }

        // Update document in ALL sessions (find the one containing this document)
        setSessions(prev => prev.map(s => ({
          ...s,
          documents: s.documents.map(d => d.id === documentId ? {
            ...d,
            type: status.document_type || d.type,
            status: status.extraction_status
          } : d)
        })))

        if (status.extraction_status === 'completed' || status.extraction_status === 'error' || status.extraction_status === 'failed') {
          console.log(`✅ Polling complete for ${documentId}: ${status.extraction_status}`)
          return
        }

        // Dynamic polling interval based on attempt number
        let pollInterval
        if (attempts < 5) {
          pollInterval = 1000   // First 5 attempts: 1s (fast feedback for quick extractions)
        } else if (attempts < 15) {
          pollInterval = 2000   // Next 10 attempts: 2s (normal polling)
        } else {
          pollInterval = 3000   // After 15 attempts: 3s (slower polling for long extractions)
        }

        console.log(`   ⏱️  Next poll in ${pollInterval/1000}s`)
        setTimeout(poll, pollInterval)
      } catch (err) {
        console.error(`❌ Poll error for ${documentId}:`, err)
        // Use dynamic interval for error retries too
        const retryInterval = attempts < 5 ? 1000 : attempts < 15 ? 2000 : 3000
        setTimeout(poll, retryInterval)
      }
    }

    console.log(`🔄 Starting polling for ${documentId}`)
    setTimeout(poll, 1000)
  }

  async function onFileSelected(e) {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    
    for (const file of files) {
      await uploadFile(file)
    }
    
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function ask() {
    const q = questionInput.trim()
    if (!q || busy) return
    setBusy(true)

    // Add user message immediately for instant feedback
    const userMsg = { role: 'user', content: q }
    setSessions(prev => prev.map(s => s.id === active.id ? { ...s, messages: [...s.messages, userMsg] } : s))
    setQuestionInput('')

    // Scroll to bottom after adding user message
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)

    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, session_id: active.id })
      })
      if (!res.ok) throw new Error('Chat failed')
      const data = await res.json()
      const aiMsg = { role: 'assistant', content: data.answer, citations: data.citations || [] }
      setSessions(prev => prev.map(s => s.id === active.id ? { ...s, messages: [...s.messages, aiMsg] } : s))

      // Scroll to bottom after adding AI response
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (error) {
      console.error('Chat error:', error)
      const errorMsg = { role: 'assistant', content: 'Sorry, there was an error processing your request.' }
      setSessions(prev => prev.map(s => s.id === active.id ? { ...s, messages: [...s.messages, errorMsg] } : s))
    } finally {
      setBusy(false)
    }
  }

  function handleKeyPress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      ask()
    }
  }

  return (
    <div style={{ height: '100vh', width: '100vw', margin: 0, display: 'grid', gridTemplateColumns: '280px 1fr 360px', overflow: 'hidden', background: 'linear-gradient(135deg, #f6faff 0%, #eef2ff 100%)' }}>
      {/* Left: Sessions */}
      <aside style={{ background: 'linear-gradient(180deg, #0f172a 0%, #111827 100%)', color: '#f8fafc', padding: 14, borderRight: '1px solid rgba(255,255,255,0.06)', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 16, letterSpacing: 0.4 }}>Sessions</h2>
          <button onClick={addSession} style={{ width: 40, height: 40, borderRadius: '9999px', background: 'linear-gradient(135deg, #7c3aed, #22d3ee)', color: '#fff', border: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, lineHeight: '22px', boxShadow: '0 8px 18px rgba(124,58,237,0.35)', transition: 'transform 120ms ease' }} onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.96)')} onMouseUp={e => (e.currentTarget.style.transform = 'scale(1)')}>+</button>
        </div>
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 10 }}>
          {sessions.map(s => (
            <li key={s.id} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setActiveSessionId(s.id)} style={{ flex: 1, textAlign: 'left', padding: 12, borderRadius: 14, border: s.id === activeSessionId ? '2px solid rgba(99,102,241,0.7)' : '1px solid rgba(255,255,255,0.06)', background: s.id === activeSessionId ? 'linear-gradient(135deg, rgba(99,102,241,0.18), rgba(139,92,246,0.18))' : 'rgba(255,255,255,0.04)', color: '#f9fafb', transition: 'background 150ms, border 150ms' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{s.name}</span>
                    {s.documents.length > 0 && <span style={{ fontSize: 11, color: '#e0e7ff', background: 'rgba(99,102,241,0.25)', padding: '3px 8px', borderRadius: 999 }}>{s.documents.length}</span>}
                  </div>
                </button>
                <button onClick={() => deleteSession(s.id)} title="Delete session" aria-label="Delete session" style={{ width: 40, height: 40, borderRadius: 12, background: 'rgba(239,68,68,0.14)', color: '#fecaca', border: '1px solid rgba(239,68,68,0.35)', transition: 'transform 120ms ease' }} onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.96)')} onMouseUp={e => (e.currentTarget.style.transform = 'scale(1)')}>×</button>
              </div>
            </li>
          ))}
        </ul>
        <div style={{ marginTop: 12 }}>
          <label style={{ fontSize: 12, color: '#cbd5e1' }}>Rename</label>
          <input value={active.name} onChange={e => renameSession(active.id, e.target.value)} style={{ width: '100%', background: 'rgba(15,23,42,0.7)', color: '#f2f2f2', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: 12, outline: 'none' }} />
        </div>
      </aside>

      {/* Center: Chat */}
      <main style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
        <header style={{ padding: '14px 18px', borderBottom: '1px solid #e2e8f0', background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(10px)', borderTopLeftRadius: 16, borderBottomRightRadius: 16 }}>
          <h1 style={{ margin: 0, fontSize: 18, color: '#111827' }}>Chat</h1>
        </header>

        {/* Messages scrollable area */}
        <div style={{ padding: 18, overflowY: 'auto', flex: 1 }}>
          <div style={{ display: 'grid', gap: 12 }}>
            {active.messages.map((m, i) => (
              <div key={i} style={{ background: m.role === 'assistant' ? '#ffffff' : '#fbfdff', border: '1px solid #e5e7eb', borderRadius: 16, padding: 14, boxShadow: '0 2px 10px rgba(20,20,40,0.06)' }}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6, fontWeight: 600 }}>{m.role === 'assistant' ? 'Assistant' : 'You'}</div>
                <div style={{ color: '#111827', lineHeight: 1.65 }} className="markdown-content">
                  {m.role === 'assistant' ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  ) : (
                    m.content
                  )}
                </div>
                {m.citations && m.citations.length > 0 && (
                  <div style={{ marginTop: 10, background: 'linear-gradient(135deg, #f8fafc, #eef2ff)', border: '1px dashed #d1d5db', borderRadius: 12, padding: 10 }}>
                    <strong style={{ fontSize: 12, color: '#334155' }}>Sources</strong>
                    <ul style={{ margin: 6 }}>
                      {m.citations.map((c, j) => (
                        <li key={j} style={{ fontSize: 12, color: '#334155' }}>
                          <span style={{ fontWeight: 600, color: '#6366f1' }}>{c.document_id}</span>
                          <span style={{ marginLeft: 8, color: '#64748b' }}>(relevance: {(c.score * 100)?.toFixed?.(0)}%)</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input docked bottom */}
        <footer style={{ padding: 14, borderTop: '1px solid #e2e8f0', background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(10px)' }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              style={{ flex: 1, border: '1px solid #c7d2fe', borderRadius: 999, padding: '14px 18px', outline: 'none', background: 'linear-gradient(135deg, #ffffff, #f8fafc)' }}
              value={questionInput}
              onChange={e => setQuestionInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask a question about your statements... (Press Enter to send)"
              disabled={busy}
            />
            <button onClick={ask} disabled={busy} style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', color: '#fff', border: 'none', padding: '0 20px', borderRadius: 999, boxShadow: '0 6px 16px rgba(99,102,241,0.35)', transition: 'transform 120ms ease', opacity: busy ? 0.6 : 1, cursor: busy ? 'not-allowed' : 'pointer' }} onMouseDown={e => !busy && (e.currentTarget.style.transform = 'scale(0.98)')} onMouseUp={e => (e.currentTarget.style.transform = 'scale(1)')}>
              {busy ? 'Sending...' : 'Send'}
            </button>
          </div>
        </footer>
      </main>

      {/* Right: Files for active session with round + */}
      <aside style={{ background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)', color: '#111827', padding: 14, borderLeft: '1px solid #e5e7eb', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 16, color: '#111827' }}>Files</h2>
          <button onClick={openFilePicker} disabled={busy} aria-label="Add file" title="Add file" style={{ width: 46, height: 46, borderRadius: '9999px', background: 'linear-gradient(135deg, #10b981, #06b6d4)', color: '#fff', border: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, lineHeight: '26px', boxShadow: '0 8px 18px rgba(6,182,212,0.28)', transition: 'transform 120ms ease' }} onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.96)')} onMouseUp={e => (e.currentTarget.style.transform = 'scale(1)')}>+</button>
          <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={onFileSelected} />
        </div>
        {active.documents.length === 0 ? (
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 10 }}>No files yet.</div>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, marginTop: 14 }}>
            {active.documents.map((d, i) => {
              const progress = uploadProgressRef.current[d.id] || { status: d.status || 'processing', progress: 0 }
              const statusColor = progress.status === 'completed' ? '#10b981' : (progress.status === 'error' || progress.status === 'failed') ? '#ef4444' : '#f59e0b'

              return (
                <li key={d.id} style={{ border: '1px solid #e5e7eb', background: 'linear-gradient(135deg, #ffffff, #f8fafc)', color: '#111827', borderRadius: 14, padding: 12, marginBottom: 10, boxShadow: '0 2px 10px rgba(20,20,40,0.06)' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 8 }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }} title={d.filename}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{i + 1}. {d.filename}</div>
                        {d.type && (
                          <div style={{ fontSize: 12, color: '#6366f1', background: 'rgba(99,102,241,0.1)', padding: '2px 8px', borderRadius: 999, display: 'inline-block' }}>
                            {d.type}
                          </div>
                        )}
                      </div>
                    </div>
                    {progress.status !== 'completed' && progress.status !== 'error' && progress.status !== 'failed' && (
                      <div>
                        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{progress.status === 'uploading' ? 'Uploading...' : progress.status === 'extracting' ? 'Extracting...' : 'Processing...'}</div>
                        <div style={{ width: '100%', height: 4, background: '#e5e7eb', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ width: `${progress.progress}%`, height: '100%', background: statusColor, transition: 'width 300ms' }} />
                        </div>
                      </div>
                    )}
                    {progress.status === 'completed' && (
                      <div style={{ fontSize: 11, color: '#10b981', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span>✓</span> Ready
                      </div>
                    )}
                    {progress.status === 'error' && (
                      <div style={{ fontSize: 11, color: '#ef4444' }}>✗ Error processing</div>
                    )}
                    {progress.status === 'failed' && (
                      <div style={{ fontSize: 11, color: '#ef4444' }}>✗ Extraction failed (ADE error)</div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </aside>
    </div>
  )
}
