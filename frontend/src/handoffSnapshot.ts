import { verifiedReceipt, type Action, type Confirmation, type Receipt } from './contracts.ts'

type Base = { sequence: number; turn_id: string; kind: string; recorded_at: string }
export type SnapshotEvent = Base & (
  | { trust: 'customer_provided' | 'adapter_provided'; verified: false; text: string; text_truncated: boolean }
  | { trust: 'backend'; verified: true; status: 'read_verified'; tool: 'get_cards' | 'get_card' | 'get_movements'; facts: ReadFacts }
  | { trust: 'backend'; verified: boolean; status: 'pending' | 'executed' | 'cancelled' | 'expired' | 'stale'; confirmation_id: string; command: { action: Action; product_id: string; transaction_id?: string; process_date?: string }; receipt?: Receipt }
  | { trust: 'backend'; verified: false; status: 'failed_or_unknown'; code?: string; tool?: string; tool_error?: string }
  | { trust: 'backend'; verified: false; status: string; handoff_id: string; persisted: true }
  | { trust: 'backend' | 'untrusted'; verified: false; status: 'unknown' }
)
export type ReadFacts = {
  release_id?: string; mode?: string; semantics?: string; source_kind?: string; product_id?: string
  cards?: { product_id?: string; simulator_state?: string; source_kind?: string; currency?: string; current_balance?: string; credit_limit?: string | null; balance_semantics?: string }[]
  movements?: { transaction_id?: string; transaction_date?: string; process_date?: string; amount?: string; currency?: string; transaction_status?: string }[]
  rows_truncated: boolean
}
export type HandoffSnapshot = {
  contract_version: 'handoff-conversation-v1'; source: 'persisted_conversation_events'
  conversation_id: string; last_sequence: number; events_truncated: boolean; events: SnapshotEvent[]
}
export function snapshotFact(value: string | null | undefined): string {
  return value?.trim() ? value : '—'
}
export function snapshotDiagnostics(event: SnapshotEvent): string[] {
  if (!('status' in event) || event.status !== 'failed_or_unknown') return []
  return [
    'code' in event ? event.code : undefined,
    'tool' in event ? event.tool : undefined,
    'tool_error' in event ? event.tool_error : undefined,
  ].filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
}
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const id = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{32}$/.test(v)
const text = (v: unknown): v is string => typeof v === 'string' && v.length <= 500
const date = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v))
const actions = ['pause', 'block', 'reactivate', 'activate', 'replacement', 'unrecognized-charge']
function snapshotCommand(v: unknown): boolean {
  if (!object(v) || !text(v.product_id) || !/\S/.test(v.product_id) || !actions.includes(String(v.action))) return false
  const charge = v.action === 'unrecognized-charge'
  if (!Object.keys(v).every(k => (charge ? ['action', 'product_id', 'transaction_id', 'process_date'] : ['action', 'product_id']).includes(k))) return false
  if (v.transaction_id !== undefined && (typeof v.transaction_id !== 'string' || Array.from(v.transaction_id).length > 30 || !/\S/.test(v.transaction_id))) return false
  if (v.process_date !== undefined) {
    if (typeof v.process_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v.process_date) || Number(v.process_date.slice(0, 4)) < 1) return false
    const parsed = Date.parse(`${v.process_date}T00:00:00Z`)
    if (!Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0, 10) !== v.process_date) return false
  }
  return true
}
const optionalText = (v: Record<string, unknown>, keys: string[]) => keys.every(k => v[k] === undefined || text(v[k]))
const only = (v: Record<string, unknown>, fields: string[]) => Object.keys(v).every(k => ['sequence', 'turn_id', 'kind', 'recorded_at', 'trust', 'verified', ...fields].includes(k))
function readFacts(v: unknown, tool: string): boolean {
  if (!object(v) || typeof v.rows_truncated !== 'boolean' || !optionalText(v, ['release_id', 'mode', 'semantics', 'source_kind', 'product_id'])) return false
  const rows = tool === 'get_movements' ? v.movements : v.cards
  const fields = tool === 'get_movements' ? ['transaction_id', 'transaction_date', 'process_date', 'amount', 'currency', 'transaction_status'] : ['product_id', 'simulator_state', 'source_kind', 'currency', 'current_balance', 'balance_semantics']
  if (tool === 'get_movements' ? v.cards !== undefined : v.movements !== undefined) return false
  return Array.isArray(rows) && rows.length <= 10 && rows.every(row => object(row) && optionalText(row, fields) && (row.credit_limit == null || text(row.credit_limit)))
}
function validEvent(v: unknown): v is SnapshotEvent {
  if (!object(v) || !Number.isInteger(v.sequence) || Number(v.sequence) < 1 || !id(v.turn_id) || !text(v.kind) || !date(v.recorded_at)) return false
  if (['user_message', 'answer', 'clarification'].includes(String(v.kind))) {
    return only(v, ['text', 'text_truncated']) && v.trust === (v.kind === 'user_message' ? 'customer_provided' : 'adapter_provided') && v.verified === false && typeof v.text === 'string' && Array.from(v.text).length <= 200 && typeof v.text_truncated === 'boolean'
  }
  if (v.status === 'unknown') return only(v, ['status']) && ['backend', 'untrusted'].includes(String(v.trust)) && v.verified === false
  if (v.trust !== 'backend') return false
  if (v.kind === 'tool_result') return only(v, ['status', 'tool', 'facts']) && v.verified === true && v.status === 'read_verified' && ['get_cards', 'get_card', 'get_movements'].includes(String(v.tool)) && readFacts(v.facts, String(v.tool))
  if (['confirmation_prepared', 'confirmation_status'].includes(String(v.kind))) {
    if (!only(v, ['status', 'confirmation_id', 'command', 'receipt']) || !id(v.confirmation_id) || !snapshotCommand(v.command) || !['pending', 'executed', 'cancelled', 'expired', 'stale'].includes(String(v.status))) return false
    if (v.verified === false) return v.receipt === undefined
    return v.verified === true && verifiedReceipt({ status: String(v.status), verified: true, simulated: true, command: v.command, evidence: v.receipt } as Confirmation) !== null
  }
  if (v.kind === 'error') return only(v, ['status', 'code', 'tool', 'tool_error']) && v.verified === false && v.status === 'failed_or_unknown' && optionalText(v, ['code', 'tool', 'tool_error'])
  if (['handoff_created', 'handoff_status'].includes(String(v.kind))) return only(v, ['status', 'handoff_id', 'persisted']) && v.verified === false && v.persisted === true && id(v.handoff_id) && ['queued', 'assigned', 'accepted', 'resolved', 'cancelled'].includes(String(v.status))
  return false
}
export function validHandoffSnapshot(v: unknown): v is HandoffSnapshot {
  if (!object(v) || v.contract_version !== 'handoff-conversation-v1' || v.source !== 'persisted_conversation_events' || !id(v.conversation_id) || !Number.isInteger(v.last_sequence) || Number(v.last_sequence) < 0 || typeof v.events_truncated !== 'boolean' || !Array.isArray(v.events) || v.events.length > 20 || !v.events.every(validEvent)) return false
  const last = Number(v.last_sequence)
  if (v.events.length === 0) return last === 0 && v.events_truncated === false
  if (v.events[v.events.length - 1].sequence !== last) return false
  return v.events.every((event, i, events) => event.sequence <= last &&
    (i === 0 || event.sequence > events[i - 1].sequence) &&
    (v.events_truncated || event.sequence === i + 1))
}
