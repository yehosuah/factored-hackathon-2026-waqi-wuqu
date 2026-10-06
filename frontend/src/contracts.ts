import { validTimestamp } from './dates.ts'
import { validHandoffSnapshot, type HandoffSnapshot } from './handoffSnapshot.ts'

export type Card = {
  product_id: string
  product_type: string
  last_four: string
  currency: string
  current_balance: string | null
  credit_limit?: string | null
  last_updated?: string | null
  simulator_state: string
  source_kind: string
  balance_semantics: string
}
export type Cards = { release_id: string; cards: Card[] }
export function cardLabel(productId: string, cards: Card[], label: (value: string) => string = value => value): string {
  const card = cards.find(card => card.product_id === productId)
  return card ? `${label(card.product_type)} · ${card.last_four}` : productId
}
export type Movement = {
  transaction_id: string
  transaction_date: string
  process_date: string
  amount: string | null
  currency: string
  transaction_type: string
  transaction_status: string
  merchant_name: string | null
}
export type Movements = {
  release_id: string
  movements: Movement[]
  next_cursor: string | null
}
export type Action =
  | 'pause'
  | 'block'
  | 'reactivate'
  | 'activate'
  | 'replacement'
  | 'unrecognized-charge'
export type Receipt = {
  action_id: string
  product_id: string
  action: Action
  status: 'succeeded'
  outcome: string
  simulator_state: string
  simulated: true
  source_kind: string
  release_id: string
  request_id?: string | null
}
export type Confirmation = {
  confirmation_id: string
  command: {
    product_id: string
    action: Action
    transaction_id?: string | null
    process_date?: string | null
  }
  status: string
  verified: boolean
  simulated: boolean
  expires_at: string
  evidence?: Receipt
}
export type Adapter = {
  provider: string
  version: string
  mode: 'stub' | 'disabled' | 'injected'
}
export function adapterKind(adapter: Adapter): 'stub' | 'disabled' | 'classifier' | 'injected' {
  if (adapter.mode !== 'injected') return adapter.mode
  return adapter.provider === 'intent-classifier' ? 'classifier' : 'injected'
}
export type ConversationEvent = {
  event_id: string
  sequence: number
  kind: string
  trust: 'untrusted' | 'backend'
  data: Record<string, unknown>
  confirmation_id: string | null
  handoff_id: string | null
  adapter: Adapter
}
export type Conversation = {
  conversation_id: string
  adapter: Adapter
  events: ConversationEvent[]
  next_after: number | null
  last_sequence: number
}
export type Handoff = {
  handoff_id: string
  status: string
  reason: string
  severity: string
  assigned_agent_id: string | null
  queue: string | null
  release_id: string
  triage: { language: string }
  model_context: {
    summary?: string
    context?: string
    unresolved_questions?: string[]
  }
  verified_evidence: {
    source: string
    release_id: string
    actions: { receipt: Receipt; committed_at: string }[]
  }
  persisted: boolean
  conversation_snapshot?: HandoffSnapshot | null
}
const states = [
  'ACTIVE',
  'PAUSED',
  'PENDING_ACTIVATION',
  'BLOCKED',
  'CLOSED',
  'INELIGIBLE',
]
export function verifiedReceipt(confirmation: Confirmation): Receipt | null {
  const r = confirmation.evidence
  const expected: Partial<Record<Action, string>> = {
    pause: 'PAUSED',
    block: 'BLOCKED',
    activate: 'ACTIVE',
    reactivate: 'ACTIVE',
  }
  if (
    !r ||
    confirmation.status !== 'executed' ||
    confirmation.verified !== true ||
    confirmation.simulated !== true ||
    !['pause', 'block', 'reactivate', 'activate', 'replacement', 'unrecognized-charge'].includes(r.action) ||
    r.simulated !== true ||
    r.status !== 'succeeded' ||
    typeof r.action_id !== 'string' ||
    typeof r.product_id !== 'string' || !r.product_id ||
    typeof r.release_id !== 'string' ||
    (r.request_id != null && (typeof r.request_id !== 'string' || !/^[0-9a-f]{32}$/.test(r.request_id))) ||
    !/^[0-9a-f]{32}$/.test(r.action_id) ||
    r.product_id !== confirmation.command.product_id ||
    r.action !== confirmation.command.action ||
    !states.includes(r.simulator_state) ||
    !r.release_id ||
    !['team_synthetic', 'organizer_synthetic'].includes(r.source_kind)
  )
    return null
  if (
    expected[r.action]
      ? r.outcome !== 'state_change_verified' ||
        r.simulator_state !== expected[r.action]
      : r.outcome !==
          (r.action === 'replacement'
            ? 'replacement_request_registered'
            : 'request_registered_for_human_review') ||
        !r.request_id ||
        !/^[0-9a-f]{32}$/.test(r.request_id)
  )
    return null
  return r
}
export function mergeEvents(
  previous: ConversationEvent[],
  incoming: ConversationEvent[],
) {
  return [
    ...new Map(
      [...previous, ...incoming].map((event) => [event.event_id, event]),
    ).values(),
  ].sort((a, b) => a.sequence - b.sequence)
}

export function availableActions(state: string): Action[] {
  const primary: Record<string, Action[]> = {
    ACTIVE: ['pause', 'block', 'replacement'],
    PAUSED: ['reactivate', 'block', 'replacement'],
    PENDING_ACTIVATION: ['activate', 'block', 'replacement'],
    BLOCKED: ['replacement'],
    INELIGIBLE: ['block', 'replacement'],
    CLOSED: [],
  }
  return Object.hasOwn(primary, state) ? primary[state] : []
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const string = (value: unknown): value is string => typeof value === 'string'
export function validAdapter(value: unknown): value is Adapter {
  return object(value) &&
    ['provider', 'version'].every(key => string(value[key]) && value[key].length > 0 && value[key].length <= 100) &&
    ['stub', 'disabled', 'injected'].includes(String(value.mode))
}
export function validCards(value: unknown): value is Cards {
  return object(value) && string(value.release_id) && Array.isArray(value.cards) && value.cards.every(c => object(c) && ['product_id', 'product_type', 'last_four', 'currency', 'simulator_state', 'source_kind', 'balance_semantics'].every(key => string(c[key])) && (c.current_balance === null || string(c.current_balance)) &&
    (c.credit_limit == null || (string(c.credit_limit) && /^-?\d+(?:\.\d+)?$/.test(c.credit_limit))) &&
    (c.last_updated == null || validTimestamp(c.last_updated)))
}
export type ConversationRead = { kind: 'cards'; value: Cards } | { kind: 'movements'; value: Movements }
export function conversationRead(event: ConversationEvent): ConversationRead | null {
  if (event.trust !== 'backend' || event.kind !== 'tool_result') return null
  const result = event.data.result
  if (event.data.tool === 'get_cards' && validCards(result)) return { kind: 'cards', value: result }
  if (event.data.tool === 'get_card' && object(result)) {
    const cards = { release_id: result.release_id, cards: [result.card] }
    if (validCards(cards)) return { kind: 'cards', value: cards }
  }
  if (event.data.tool === 'get_movements' && validMovements(result)) return { kind: 'movements', value: result }
  return null
}
export function validConfirmation(value: unknown): value is Confirmation {
  return object(value) && string(value.confirmation_id) && /^[0-9a-f]{32}$/.test(value.confirmation_id) && object(value.command) && string(value.command.product_id) && (value.command.transaction_id == null || string(value.command.transaction_id)) && (value.command.process_date == null || string(value.command.process_date)) && ['pause', 'block', 'reactivate', 'activate', 'replacement', 'unrecognized-charge'].includes(String(value.command.action)) && ['pending', 'executed', 'cancelled', 'expired', 'stale'].includes(String(value.status)) && typeof value.verified === 'boolean' && typeof value.simulated === 'boolean' && string(value.expires_at)
}
export function validConversation(value: unknown): value is Conversation {
  return object(value) && string(value.conversation_id) && /^[0-9a-f]{32}$/.test(value.conversation_id) && validAdapter(value.adapter) && Array.isArray(value.events) && value.events.every(e => object(e) && string(e.event_id) && Number.isInteger(e.sequence) && string(e.kind) && ['backend', 'untrusted'].includes(String(e.trust)) && object(e.data)) && (value.next_after === null || Number.isInteger(value.next_after))
}
export function validChargeIdentity(command: Confirmation['command']): boolean {
  const date = command.process_date
  if (!command.transaction_id?.trim() || !date || !/^\d{4}-\d{2}-\d{2}$/.test(date) || Number(date.slice(0, 4)) < 1) return false
  const parsed = Date.parse(`${date}T00:00:00Z`)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === date
}
export function validHandoff(value: unknown): value is Handoff {
  if (!object(value) ||
      !['handoff_id', 'status', 'reason', 'severity', 'release_id'].every(key => string(value[key])) ||
      !String(value.handoff_id).trim() ||
      !(value.assigned_agent_id === null || string(value.assigned_agent_id)) ||
      !(value.queue === null || string(value.queue)) ||
      typeof value.persisted !== 'boolean' ||
      !object(value.triage) || !string(value.triage.language) ||
      !object(value.model_context) || !object(value.verified_evidence)) return false
  if (value.conversation_snapshot != null && !validHandoffSnapshot(value.conversation_snapshot)) return false
  const context = value.model_context
  if ((context.summary !== undefined && !string(context.summary)) ||
      (context.context !== undefined && !string(context.context)) ||
      (context.unresolved_questions !== undefined &&
        (!Array.isArray(context.unresolved_questions) || !context.unresolved_questions.every(string)))) return false
  const evidence = value.verified_evidence
  return string(evidence.source) && string(evidence.release_id) &&
    Array.isArray(evidence.actions) && evidence.actions.every(a =>
      object(a) && string(a.committed_at) && object(a.receipt) &&
      verifiedReceipt({ status: 'executed', verified: true, simulated: true,
        command: { product_id: a.receipt.product_id, action: a.receipt.action },
        evidence: a.receipt } as Confirmation) !== null)
}
export function validMovements(value: unknown): value is Movements {
  return object(value) && string(value.release_id) && (value.next_cursor === null || string(value.next_cursor)) && Array.isArray(value.movements) && value.movements.every(m => object(m) && ['transaction_id', 'transaction_date', 'process_date', 'currency', 'transaction_type', 'transaction_status'].every(key => string(m[key])) && (m.amount === null || string(m.amount)) && (m.merchant_name === null || string(m.merchant_name)))
}
