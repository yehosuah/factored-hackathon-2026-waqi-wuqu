import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from 'react'
import { Demo } from './demo'
import { ChatPage } from './ChatPage'
import { Header } from './Header'
import { HomePage } from './HomePage'
import { CardsPage } from './CardsPage'
import { messages, translateStatus, type Locale, type Messages } from './i18n'
import {
  verifiedReceipt, validChargeIdentity,
  conversationRead,
  cardLabel,
  type Card,
  type Receipt,
  type ConversationEvent,
  type Handoff,
  type Confirmation,
} from './contracts'
import { money, sourceDate, sourceLabel, workflowCopy } from './workflow-copy'
import { snapshotFact, snapshotDiagnostics, type HandoffSnapshot, type SnapshotEvent } from './handoffSnapshot'
const demo = new Demo()
const productName = "Waqi'wuqu"
function ReceiptView({
  receipt: r,
  text,
  locale,
}: {
  receipt: Receipt
  text: Messages
  locale: Locale
}) {
  return (
    <div className="receipt">
      <strong>{text.receipt}</strong>
      <p>
        {text[r.action]} · {translateStatus(text, r.simulator_state)}
      </p>
      <details>
        <summary>{text.trace}</summary>
        <dl>
          <dt>{text.actionId}</dt>
          <dd>{r.action_id}</dd>
          <dt>{text.product}</dt>
          <dd>{r.product_id}</dd>
          <dt>{text.outcome}</dt>
          <dd>{sourceLabel(r.outcome, locale)}</dd>
          <dt>{text.source}</dt>
          <dd>{sourceLabel(r.source_kind, locale)}</dd>
          <dt>{text.release}</dt>
          <dd>{r.release_id}</dd>
          {r.request_id && (
            <>
              <dt>{text.requestId}</dt>
              <dd>{r.request_id}</dd>
            </>
          )}
        </dl>
      </details>
    </div>
  )
}
function EventView({
  event: e,
  text,
  locale,
}: {
  event: ConversationEvent
  text: Messages
  locale: Locale
}) {
  const prose = typeof e.data.text === 'string' ? e.data.text : ''
  const read = conversationRead(e)
  const result =
    e.data.result && typeof e.data.result === 'object'
      ? (e.data.result as Record<string, unknown>)
      : null
  const status =
    typeof result?.status === 'string'
      ? translateStatus(text, result.status)
      : text.refresh
  return (
    <li className={`event ${e.trust} ${e.kind}`}>
      {e.trust === 'untrusted' && (
        <small>
          {e.kind === 'user_message' ? text.customer : text.untrusted}
        </small>
      )}
      {e.kind === 'clarification' && <strong>{text.clarification}</strong>}
      {prose && <p>{prose}</p>}
      {e.kind === 'error' && (
        <div role="alert">
          <p>{text.eventError}</p>
          <details>
            <summary>{text.trace}</summary>
            <code>{typeof e.data.code === 'string' ? e.data.code : ''}</code>
          </details>
        </div>
      )}
      {e.trust === 'backend' && e.kind === 'tool_result' && (
        <>
          <strong>{read?.kind === 'cards' ? text.listedCards : read?.kind === 'movements' ? text.movements : text.tool}</strong>
          {!read && <p role="alert">{text.invalid_response}</p>}
          {read?.kind === 'cards' && (
            <ol className="read-cards">
              {read.value.cards.map(card => (
                <li key={card.product_id}>
                  <p>{sourceLabel(card.product_type, locale)} · {card.last_four}</p>
                  <p>{text.status}: {translateStatus(text, card.simulator_state)}</p>
                  <p>{text.balance}: {money(card.current_balance, card.currency, locale)}</p>
                  <p>{text.creditLimit}: {card.credit_limit == null ? text.limitUnavailable : money(card.credit_limit, card.currency, locale)}</p>
                  {card.last_updated && <p>{text.productUpdated}: <time dateTime={card.last_updated}>{sourceDate(card.last_updated, locale)}</time></p>}
                </li>
              ))}
            </ol>
          )}
          {read?.kind === 'cards' && read.value.cards.length === 0 && <p>{text.noCards}</p>}
          {read?.kind === 'movements' && (
            <ul className="read-movements">
              {read.value.movements.map(movement => (
                <li key={`${movement.transaction_id}:${movement.process_date}`}>
                  <p>{sourceDate(movement.transaction_date, locale)} · {movement.merchant_name ?? sourceLabel(movement.transaction_type, locale)}</p>
                  <p>{money(movement.amount, movement.currency, locale)} · {sourceLabel(movement.transaction_status, locale)}</p>
                </li>
              ))}
            </ul>
          )}
          {read?.kind === 'movements' && read.value.movements.length === 0 && <p>{text.empty}</p>}
          {read && <small>{text.historical}</small>}
          <details>
            <summary>{text.trace}</summary>
            <p>{typeof e.data.tool === 'string' ? e.data.tool : ''}</p>
            {read && <p>{text.release}: {read.value.release_id}</p>}
          </details>
        </>
      )}
      {e.trust === 'backend' && e.confirmation_id && (
        <p>{e.kind === 'confirmation_prepared' ? text.stepTwo : status}</p>
      )}
      {e.trust === 'backend' && e.handoff_id && (
        <p>
          {text.handoffs} · {status}
        </p>
      )}
    </li>
  )
}
function SnapshotEventView({ event: e, text, locale }: { event: SnapshotEvent; text: Messages; locale: Locale }) {
  return (
    <li className={`event ${e.trust}`}>
      {'text' in e && <><small>{e.trust === 'customer_provided' ? text.customer : text.untrusted}</small><p>{e.text}</p>{e.text_truncated && <small>{text.excerptTruncated}</small>}</>}
      {'facts' in e && <>
        <strong>{text.savedRead}</strong>
        <ul className="read-cards">
          {e.facts.cards?.map((c, i) => <li key={i}><p>{text.product}: {snapshotFact(c.product_id)} · {translateStatus(text, snapshotFact(c.simulator_state))}</p><p>{text.balance}: {snapshotFact(c.current_balance)} {snapshotFact(c.currency)}</p><p>{text.creditLimit}: {c.credit_limit == null ? text.limitUnavailable : `${snapshotFact(c.credit_limit)} ${snapshotFact(c.currency)}`}</p></li>)}
          {e.facts.movements?.map((m, i) => <li key={i}><p>{snapshotFact(m.transaction_date?.slice(0, 10))} · {snapshotFact(m.transaction_id)}</p><p>{snapshotFact(m.amount)} {snapshotFact(m.currency)} · {snapshotFact(m.transaction_status)}</p></li>)}
        </ul>
        {e.facts.cards?.length === 0 && <p>{text.noCards}</p>}
        {e.facts.movements?.length === 0 && <p>{text.empty}</p>}
        {e.facts.rows_truncated && <small>{text.rowsTruncated}</small>}
        <details><summary>{text.trace}</summary><p>{e.tool}{e.facts.product_id ? ` · ${e.facts.product_id}` : ''}</p><p>{text.release}: {snapshotFact(e.facts.release_id)}</p><p>{text.source}: {snapshotFact(e.facts.source_kind)}</p></details>
      </>}
      {'command' in e && <><strong>{translateStatus(text, e.command.action)} · {e.command.product_id}</strong><p>{translateStatus(text, e.status)}</p>{e.command.action === 'unrecognized-charge' && <><p>{text.requestedMovement}: {snapshotFact(e.command.transaction_id)}</p><p>{text.processDate}: {snapshotFact(e.command.process_date)}</p></>}{e.receipt ? <ReceiptView receipt={e.receipt} text={text} locale={locale} /> : e.status === 'executed' && <p>{text.untrusted}</p>}</>}
      {'status' in e && e.status === 'failed_or_unknown' && <><strong>{text.failedAttempt}</strong><p>{text.eventError}</p>{snapshotDiagnostics(e).length > 0 && <details><summary>{text.trace}</summary>{snapshotDiagnostics(e).map((value, i) => <p key={i}>{value}</p>)}</details>}</>}
      {'handoff_id' in e && <p>{text.handoffs} · {translateStatus(text, e.status)}</p>}
      {'status' in e && e.status === 'unknown' && <p>{text.unknownAttempt}</p>}
    </li>
  )
}
function SnapshotView({ snapshot, text, locale }: { snapshot: HandoffSnapshot; text: Messages; locale: Locale }) {
  return <details className="handoff-snapshot"><summary>{text.savedConversation}</summary><p className="muted">{text.snapshotNote}</p>{snapshot.events_truncated && <p>{text.historyTruncated}</p>}<ol className="events">{snapshot.events.map(e => <SnapshotEventView key={e.sequence} event={e} text={text} locale={locale} />)}</ol></details>
}
function HandoffView({
  handoff: h,
  text,
  locale,
  role,
  locked,
}: {
  handoff: Handoff
  text: Messages
  locale: Locale
  role: string
  locked: boolean
}) {
  return (
    <article className="case">
      <div className="section-heading">
        <h3>{translateStatus(text, h.status)}</h3>
        <span className="pill">{h.triage.language.toUpperCase()}</span>
      </div>
      <p className="case-summary">{h.model_context.summary}</p>
      <p className="muted">
        {text.agent}: {h.assigned_agent_id ?? (h.queue ? sourceLabel(h.queue, locale) : '—')}
      </p>
      <details>
        <summary>{text.context}</summary>
        <p>{h.model_context.context}</p>
        {h.model_context.unresolved_questions?.map((q) => (
          <p key={q}>{q}</p>
        ))}
        <small className="mono">{h.handoff_id}</small>
      </details>
      {h.conversation_snapshot && <SnapshotView snapshot={h.conversation_snapshot} text={text} locale={locale} />}
      <details>
        <summary>{text.evidence}</summary>
        <p>
          {text.release}: {h.verified_evidence.release_id}
        </p>
        {h.verified_evidence.actions.map((a) => (
          <ReceiptView
            key={a.receipt.action_id}
            receipt={a.receipt}
            locale={locale}
            text={text}
          />
        ))}
      </details>
      <div className="actions">
        {role === 'agent' && h.status === 'assigned' && (
          <button
            disabled={locked}
            onClick={() => void demo.transition(h.handoff_id, 'accept')}
          >
            {text.accept}
          </button>
        )}
        {role === 'agent' && h.status === 'accepted' && (
          <button
            disabled={locked}
            onClick={() => void demo.transition(h.handoff_id, 'resolve')}
          >
            {text.resolve}
          </button>
        )}
        {role === 'customer' && ['queued', 'assigned'].includes(h.status) && (
          <button
            className="secondary"
            disabled={locked}
            onClick={() => void demo.transition(h.handoff_id, 'cancel')}
          >
            {text.cancel}
          </button>
        )}
      </div>
    </article>
  )
}
function ConfirmationView({
  confirmation: c,
  text,
  locked,
  review,
  locale,
  reportCase,
  cards,
}: {
  confirmation: Confirmation
  text: Messages
  locked: boolean
  review: (id: string) => void
  locale: Locale
  reportCase?: string
  cards: Card[]
}) {
  const receipt = verifiedReceipt(c)
  const copy = workflowCopy[locale]
  const canReport = validChargeIdentity(c.command)
  return (
    <article className={`confirmation ${c.status}`}>
      <div className="section-heading">
        <h3>{text[c.command.action]}</h3>
        <span className="pill">{translateStatus(text, c.status)}</span>
      </div>
      <p>
        {text.product} · {cardLabel(c.command.product_id, cards, value => sourceLabel(value, locale))}
      </p>
      {c.command.transaction_id && (
        <p>
          {c.command.transaction_id} · {c.command.process_date}
        </p>
      )}
      {receipt && <ReceiptView receipt={receipt} text={text} locale={locale} />}
      {receipt?.action === 'unrecognized-charge' && <div className="charge-followup">
        <p>{copy.reviewOnly}</p>
        {reportCase ? <p role="status">{copy.reported}: <a href="#home-cases">{reportCase}</a></p> : <>
          <button disabled={locked || !canReport} onClick={() => void demo.reportCharge(c.confirmation_id, locale)}>{copy.report}</button>
          {!canReport && <p>{copy.chargeIdentityMissing}</p>}
        </>}
        <details><summary>{text.context}</summary><p>{copy.caseScope}</p></details>
      </div>}
      <div className="actions">
        {c.status === 'pending' && (
          <button disabled={locked} onClick={() => review(c.confirmation_id)}>
            {text.review}
          </button>
        )}
        <button
          className="text-button"
          disabled={locked}
          onClick={() => void demo.confirmation(c.confirmation_id, 'refresh')}
        >
          {text.refresh}
        </button>
      </div>
      <details className="trace">
        <summary>{text.trace}</summary>
        <p className="mono">{c.confirmation_id}</p>
        <p className="mono">{c.command.product_id}</p>
        <p>
          {text.expires}: {c.expires_at}
        </p>
      </details>
    </article>
  )
}
function ConfirmDialog({
  confirmation: c,
  text,
  locked,
  busy,
  error,
  retryable,
  locale,
  close,
  cards,
}: {
  confirmation: Confirmation | undefined
  text: Messages
  locked: boolean
  busy: boolean
  error: string
  retryable: boolean
  locale: Locale
  close: () => void
  cards: Card[]
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (c && c.status === 'pending') ref.current?.showModal()
    else ref.current?.close()
  }, [c])
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClose={close}
      aria-labelledby="confirm-heading"
    >
      <div className="dialog-content">
        <p className="eyebrow">{text.stepTwo}</p>
        <h2 id="confirm-heading">{text.confirmTitle}</h2>
        <p className="muted">{text.confirmBody}</p>
        {c?.command.action === 'unrecognized-charge' && <p className="workflow-note">{workflowCopy[locale].chargeConfirm}</p>}
        {c?.command.action === 'block' && <p className="workflow-note">{workflowCopy[locale].blockHelp}</p>}
        {busy && (
          <div className="feedback" role="status">
            <span>{text.loading}</span>
            <button
              className="text-button"
              onClick={() => demo.cancelRequest()}
            >
              {text.cancelRequest}
            </button>
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            <p>{Object.hasOwn(text, error) ? text[error as keyof Messages] : text.error}</p>
            {retryable && (
              <>
                <p>{text.retryHelp}</p>
                <button disabled={busy} onClick={() => void demo.retry()}>
                  {text.retry}
                </button>
              </>
            )}
          </div>
        )}
        {c && (
          <>
            <dl className="review-facts">
              <dt>{text.command}</dt>
              <dd>{text[c.command.action]}</dd>
              <dt>{text.product}</dt>
              <dd>{cardLabel(c.command.product_id, cards, value => sourceLabel(value, locale))}</dd>
              <dt>{text.expires}</dt>
              <dd>{c.expires_at}</dd>
            </dl>
            {c.command.transaction_id && (
              <p>
                {c.command.transaction_id} · {c.command.process_date}
              </p>
            )}
            <button
              className="confirm-button"
              disabled={locked}
              onClick={() =>
                void demo.confirmation(c.confirmation_id, 'confirm')
              }
            >
              {text.confirm}
            </button>
            <div className="actions">
              <button
                className="secondary"
                disabled={locked}
                onClick={() =>
                  void demo.confirmation(c.confirmation_id, 'cancel')
                }
              >
                {text.cancel}
              </button>
              <button
                className="text-button"
                disabled={locked}
                onClick={() =>
                  void demo.confirmation(c.confirmation_id, 'refresh')
                }
              >
                {text.refresh}
              </button>
              <button className="text-button" onClick={close}>
                {text.close}
              </button>
            </div>
          </>
        )}
      </div>
    </dialog>
  )
}
export default function App() {
  const state = useSyncExternalStore(demo.subscribe, demo.snapshot)
  const [locale, setLocale] = useState<Locale>('es')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [summary, setSummary] = useState('')
  const [reviewId, setReviewId] = useState('')
  const [route, setRoute] = useState(window.location.hash)
  const page = route === '#chat' ? 'chat' : ['#cards', '#cards-title'].includes(route) ? 'cards' : 'home'
  const chatPage = state.signedIn && state.role === 'customer' && page === 'chat'
  const text = messages[locale]
  const locked = state.busy || state.retryable
  useEffect(() => {
    const navigate = () => {
      if (window.location.hash !== '#main') setRoute(window.location.hash)
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [page])
  useEffect(() => {
    document.documentElement.lang = locale
    document.title = state.signedIn && state.role === 'customer' ? `${productName} · ${page === 'chat' ? text.chat : page === 'cards' ? text.cards : text.home}` : text.pageTitle
  }, [locale, text.pageTitle, text.chat, text.cards, text.home, state.signedIn, state.role, page])
  useEffect(() => {
    let previous = demo.snapshot()
    return demo.subscribe(() => {
      const next = demo.snapshot()
      if (previous.signedIn && !next.signedIn) {
        setUsername('')
        setPassword('')
        setSummary('')
        setReviewId('')
      }
      previous = next
    })
  }, [])
  function login(event: FormEvent) {
    event.preventDefault()
    const secret = password
    setPassword('')
    void demo.login(state.role, username, secret)
  }
  function logout() {
    setUsername('')
    setPassword('')
    setSummary('')
    setReviewId('')
    void demo.logout()
  }
  async function review(id: string) {
    setReviewId('')
    const current = await demo.reviewConfirmation(id)
    if (current && demo.snapshot().signedIn) setReviewId(current.confirmation_id)
  }
  return (
    <div className={`shell ${state.signedIn ? 'authenticated' : 'entry'} ${chatPage ? 'chat-page' : ''}`}>
      <a className="skip" href="#main">
        {text.overview}
      </a>
      <Header text={text} locale={locale} setLocale={setLocale} signedIn={state.signedIn} role={state.role} route={state.role === 'customer' ? `#${page}` : route} logout={logout} />
      <main id="main" tabIndex={-1}>
        <div className="feedback-region" aria-live="polite" aria-atomic="true">
          {state.busy && (
            <div className="feedback">
              <span className="spinner" aria-hidden="true" />
              <span>{text.loading}</span>
              <button
                className="text-button"
                onClick={() => demo.cancelRequest()}
              >
                {text.cancelRequest}
              </button>
            </div>
          )}
        </div>
        {state.error && (
          <div className="error" role="alert">
            <p>
              {Object.hasOwn(text, state.error)
                ? text[state.error as keyof Messages]
                : text.error}
            </p>
            {state.retryable && (
              <>
                <p>{text.retryHelp}</p>
                <button disabled={state.busy} onClick={() => void demo.retry()}>
                  {text.retry}
                </button>
              </>
            )}
          </div>
        )}
        {!state.signedIn ? (
          <div className="entry-grid">
            <section className="login">
              <h1>
                {state.role === 'customer' ? text.welcome : text.agentTitle}
              </h1>
              <form onSubmit={login}>
                <label>
                  {text.username}
                  <input
                    required
                    autoComplete="username"
                    maxLength={100}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={state.busy}
                  />
                </label>
                <label>
                  {text.password}
                  <input
                    required
                    type="password"
                    autoComplete="current-password"
                    maxLength={200}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={state.busy}
                  />
                </label>
                <button className="login-submit" disabled={state.busy}>
                  {text.login}
                </button>
              </form>
              <div className="portal-switch">
                <button
                  className="text-button"
                  disabled={state.busy}
                  onClick={() => {
                    demo.setRole(
                      state.role === 'customer' ? 'agent' : 'customer',
                    )
                    setUsername('')
                    setPassword('')
                  }}
                >
                  {state.role === 'customer' ? text.loginAgent : text.customer}
                </button>
              </div>
            </section>
          </div>
        ) : chatPage ? (
          <>
            <ChatPage state={state} demo={demo} locale={locale} renderEvent={e => <EventView key={e.event_id} event={e} text={text} locale={locale} />}>
              {state.confirmations.filter(c => state.conversation?.events.some(e => e.trust === 'backend' && e.confirmation_id === c.confirmation_id)).map(c => <ConfirmationView key={c.confirmation_id} confirmation={c} cards={state.cards} text={text} locale={locale} reportCase={c.evidence ? state.reportCases[c.evidence.action_id] : undefined} locked={locked} review={id => void review(id)} />)}
            </ChatPage>
            <ConfirmDialog cards={state.cards} locale={locale} confirmation={state.confirmations.find(c => c.confirmation_id === reviewId)} text={text} locked={locked} busy={state.busy} error={state.error} retryable={state.retryable} close={() => setReviewId('')} />
          </>
        ) : (
          <>
            {state.role === 'customer' && page === 'home' ? <HomePage state={state} text={text} locale={locale} locked={locked} refresh={() => void demo.refresh()} /> : <div className="hero"><div><h1>{state.role === 'customer' ? text.cards : text.agentTitle}</h1></div><button className="secondary" disabled={locked} onClick={() => void demo.refresh()}>{text.refresh}</button></div>}
            <p className="notice">{text.demo}</p>
            {state.role === 'customer' && page === 'cards' && (
              <>
                <CardsPage state={state} demo={demo} text={text} locked={locked} productName={productName} locale={locale} />
                {state.confirmations.length > 0 && (
                  <section className="panel">
                    <h2>{text.confirmations}</h2>
                    <div className="confirmation-grid">
                      {state.confirmations.map((c) => (
                        <ConfirmationView
                          key={c.confirmation_id}
                          confirmation={c}
                          locale={locale}
                          reportCase={c.evidence ? state.reportCases[c.evidence.action_id] : undefined}
                          text={text}
                          locked={locked}
                          review={(id) => void review(id)}
                          cards={state.cards}
                        />
                      ))}
                    </div>
                  </section>
                )}
                <ConfirmDialog
                  locale={locale}
                  confirmation={state.confirmations.find(
                    (c) => c.confirmation_id === reviewId,
                  )}
                  text={text}
                  locked={locked}
                  busy={state.busy}
                  error={state.error}
                  retryable={state.retryable}
                  close={() => setReviewId('')}
                  cards={state.cards}
                />
              </>
            )}
            {(state.role === 'agent' || page === 'home') && <section className="panel home-cases" id="home-cases" aria-labelledby="handoffs-title">
              <h2 id="handoffs-title">{text.handoffs}</h2>
              {state.role === 'customer' && (
                <details className="human-request">
                  <summary>{text.requestHandoff}</summary>
                  <form
                    className="handoff-form"
                    onSubmit={(e) => {
                      e.preventDefault()
                      void demo.handoff(summary, locale)
                      setSummary('')
                    }}
                  >
                    <label>
                      {text.summary}
                      <textarea
                        required
                        maxLength={2000}
                        value={summary}
                        disabled={locked}
                        onChange={(e) => setSummary(e.target.value)}
                      />
                    </label>
                    <button disabled={locked || !summary.trim()}>
                      {text.requestHandoff}
                    </button>
                  </form>
                </details>
              )}
              {state.handoffs.length === 0 && (
                <p className="empty-state">{text.noHandoffs}</p>
              )}
              <div className="confirmation-grid">
                {state.handoffs.map((h) => (
                  <HandoffView
                    key={h.handoff_id}
                    handoff={h}
                    locale={locale}
                    text={text}
                    role={state.role}
                    locked={locked}
                  />
                ))}
              </div>
            </section>}
          </>
        )}
      </main>
      {!state.signedIn && <footer>{text.demo}</footer>}
    </div>
  )
}
