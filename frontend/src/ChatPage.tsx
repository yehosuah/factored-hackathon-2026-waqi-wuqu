import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Demo, State } from './demo'
import type { ConversationEvent } from './contracts'
import { adapterKind } from './contracts'
import { chatCopy } from './chat-copy'
import { messages, translateStatus, type Locale } from './i18n'
import { money, sourceDate, sourceLabel, workflowCopy } from './workflow-copy'

function ChatIcon({ send = false }: { send?: boolean }) {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {send ? <><path d="m5 12 7-7 7 7M12 5v14" /></> : <><path d="M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0Z" /><path d="M7 10h8M7 14h5" /></>}
  </svg>
}

export function ChatPage({ state, demo, locale, renderEvent, children }: {
  state: State; demo: Demo; locale: Locale
  renderEvent: (event: ConversationEvent) => ReactNode; children: ReactNode
}) {
  const copy = chatCopy[locale]
  const flow = workflowCopy[locale]
  const [intent, setIntent] = useState<'pause' | 'block' | ''>('')
  const [draft, setDraft] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const history = useRef<HTMLDialogElement>(null)
  const guide = useRef<HTMLDetailsElement>(null)
  const locked = state.busy || state.retryable
  const conversation = state.conversation
  const events = conversation?.events ?? []
  const handoffIds = new Set(events.filter(e => e.trust === 'backend').map(e => e.handoff_id).filter(Boolean))
  const cases = state.handoffs.filter(h => handoffIds.has(h.handoff_id))
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }, [conversation?.conversation_id, events.length])
  useEffect(() => { if (historyOpen) history.current?.showModal(); else history.current?.close() }, [historyOpen])
  useEffect(() => {
    let previous = demo.snapshot().acknowledgedTurn
    return demo.subscribe(() => {
      const acknowledgement = demo.snapshot().acknowledgedTurn
      if (acknowledgement && acknowledgement !== previous)
        setDraft(current => current === acknowledgement.message ? '' : current)
      previous = acknowledgement
    })
  }, [demo])
  async function send(value = draft) {
    if (!value.trim() || locked) return
    if (!conversation) {
      await demo.startConversation(locale)
      if (demo.snapshot().error) return
    }
    if (!demo.snapshot().conversation || demo.snapshot().retryable) return
    await demo.turn(value, locale, demo.snapshot().chatContext?.product_id ?? null)
  }
  async function suggest(index: number) {
    if (!conversation) await demo.startConversation(locale)
    const current = demo.snapshot()
    if (!current.signedIn || current.error || !current.conversation) return
    setDraft(current.conversation.adapter.mode === 'stub' ? ['/cards', '/clarify', '/handoff'][index] : copy.prompts[index])
  }
  async function guided(action: 'pause' | 'block' | 'unrecognized-charge') {
    await demo.guidedRequest(action, locale)
    if (!demo.snapshot().error && !demo.snapshot().retryable && guide.current) guide.current.open = false
  }
  return <div className="chat-workspace" onKeyDown={e => { if (e.key === 'Escape') setHistoryOpen(false) }}>
    <dialog ref={history} className="chat-sidebar" aria-label={copy.history} onCancel={() => setHistoryOpen(false)} onClose={() => setHistoryOpen(false)}>
      <div className="history-drawer-heading"><strong>{copy.history}</strong><button className="text-button" aria-label={copy.closeHistory} onClick={() => setHistoryOpen(false)}>×</button></div>
      <a className="chat-back" href="#cards">← {copy.back}</a>
      <button className="new-chat" disabled={locked} onClick={() => { demo.newChat(); setDraft(''); setHistoryOpen(false) }}><span aria-hidden="true">＋</span>{copy.newChat}</button>
      <div className="history-heading"><span>{copy.history}</span><span>{state.conversationHistory.length.toString().padStart(2, '0')}</span></div>
      <div className="chat-history">
        {state.conversationHistory.length === 0 && <p className="history-empty">{copy.empty}</p>}
        {state.conversationHistory.map((chat) => {
          const first = chat.events.find(e => e.kind === 'user_message')
          const title = typeof first?.data.text === 'string' ? first.data.text : copy.newChat
          return <button className={`history-item ${chat.conversation_id === conversation?.conversation_id ? 'selected' : ''}`} aria-current={chat.conversation_id === conversation?.conversation_id ? 'true' : undefined} key={chat.conversation_id} disabled={locked} onClick={() => { setDraft(''); setHistoryOpen(false); void demo.openConversation(chat.conversation_id) }}><ChatIcon /><span>{title}</span></button>
        })}
      </div>
      <div className="history-note"><details><summary>{copy.session}</summary><p>{copy.sessionNote}</p></details></div>
    </dialog>
    <section className={`chat-stage ${events.length ? 'has-messages' : ''}`} aria-label={copy.title}>
      <div className="chat-topline"><button className="chat-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}><ChatIcon />{copy.history}</button><button className="chat-new-toggle" disabled={locked} onClick={() => { demo.newChat(); setDraft('') }}><span aria-hidden="true">＋</span>{copy.newChat}</button></div>
      <div className="chat-body">
        <details ref={guide} className="guided-support" open={state.chatContext?.movement ? true : undefined}>
          <summary>{flow.clarify}</summary>
          <label>{flow.cardContext}<select value={state.chatContext?.product_id ?? ''} disabled={locked} onChange={e => { demo.setChatContext(e.target.value); setIntent('') }}>
            <option value="">{flow.choose}</option>
            {state.cards.map(card => <option key={card.product_id} value={card.product_id}>{sourceLabel(card.product_type, locale)} · {card.last_four} · {translateStatus(messages[locale], card.simulator_state)}</option>)}
          </select></label>
          {state.chatContext?.movement ? <div className="movement-context">
            <strong>{flow.movementContext}</strong><p>{state.chatContext.movement.merchant_name ?? sourceLabel(state.chatContext.movement.transaction_type, locale)} · {money(state.chatContext.movement.amount, state.chatContext.movement.currency, locale)}</p>
            <p>{flow.processDate}: {sourceDate(state.chatContext.movement.process_date, locale)}</p>
            <div className="actions"><button disabled={locked || conversation?.adapter.mode === 'stub' || conversation?.adapter.mode === 'disabled'} onClick={() => void guided('unrecognized-charge')}>{flow.sendCharge}</button>
              <button className="secondary" disabled={locked} onClick={() => demo.setChatContext(state.chatContext!.product_id)}>{flow.clearMovement}</button></div>
          </div> : <>
            <fieldset disabled={locked}><legend>{flow.clarify}</legend>
              <label><input type="radio" name="card-intent" checked={intent === 'pause'} onChange={() => setIntent('pause')} />{flow.pause}</label>
              <label><input type="radio" name="card-intent" checked={intent === 'block'} onChange={() => setIntent('block')} />{flow.block}</label>
            </fieldset>
            {intent && <p>{intent === 'pause' ? flow.pauseHelp : flow.blockHelp}</p>}
            <button disabled={locked || !intent || !state.chatContext || conversation?.adapter.mode === 'disabled' || (conversation?.adapter.mode === 'stub' && intent === 'block')} onClick={() => { if (intent) void guided(intent) }}>{flow.sendChoice}</button>
          </>}
          <p className="workflow-note">{flow.selectionNote}</p>
          {conversation?.adapter.mode === 'stub' && <p>{flow.stubLimit} <a href="#cards">{copy.back}</a></p>}
          {conversation?.adapter.mode === 'disabled' && <p>{flow.disabled} <a href="#cards">{copy.back}</a></p>}
        </details>
        {events.length === 0 ? <div className="chat-welcome">
          <div className="assistant-emblem"><ChatIcon /></div><p className="eyebrow">{copy.help}</p>
          <h1>{copy.greeting}</h1><p>{copy.intro}</p>
        </div> : <div className="chat-thread"><ol className="events" aria-label={copy.messages} aria-live="polite">{events.map(renderEvent)}</ol>
          {cases.map(h => <div className="chat-transfer" key={h.handoff_id}><span className="transfer-icon"><ChatIcon /></span><div><strong>{copy.transferred}</strong><p>{translateStatus(messages[locale], h.status)}</p><p>{copy.transferNote}</p><button className="text-button" disabled={locked} onClick={() => void demo.refresh()}>{copy.refresh}</button></div></div>)}
          {children}<div ref={end} />
        </div>}
      </div>
      <div className="chat-compose-area">
        <form className="chat-composer" onSubmit={e => { e.preventDefault(); void send() }}>
          <label className="sr-only" htmlFor="chat-draft">{copy.placeholder}</label>
          <textarea id="chat-draft" placeholder={copy.placeholder} maxLength={2000} value={draft} disabled={locked} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send() } }} />
          <div className="composer-bottom"><span><ChatIcon />{copy.assistant}</span><button aria-label={copy.send} disabled={locked || !draft.trim()}><ChatIcon send /></button></div>
        </form>
        {events.length === 0 && <div className="chat-suggestions">{copy.prompts.map((prompt, i) => <button className="secondary" key={prompt} disabled={locked} onClick={() => void suggest(i)}>{prompt}<span aria-hidden="true">↗</span></button>)}</div>}
        <button className="text-button chat-human" disabled={locked || conversation?.adapter.mode === 'disabled'} onClick={() => void demo.requestConversationHandoff(locale)}>{flow.human}</button>
        <p className="chat-disclaimer">{copy.promptNote}{conversation && <> {messages[locale][adapterKind(conversation.adapter)]}</>}</p>
      </div>
    </section>
  </div>
}
