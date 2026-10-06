import { Api, ApiError, commandKey, segment, type Role } from './api.ts'
import {
  mergeEvents,
  validCards, validConfirmation, validConversation, validHandoff, validMovements,
  verifiedReceipt, validChargeIdentity,
  type Cards,
  type Card,
  type Confirmation,
  type Conversation,
  type Handoff,
  type Movements,
  type Action,
  type Movement,
} from './contracts.ts'
import type { Locale } from './i18n.ts'
import { workflowCopy } from './workflow-copy.ts'
export type State = {
  role: Role
  signedIn: boolean
  username: string
  busy: boolean
  error: string
  retryable: boolean
  acknowledgedTurn: { key: string; message: string } | null
  cards: Card[]
  release: string
  movements: Movements | null
  selected: string
  conversation: Conversation | null
  conversationHistory: Conversation[]
  confirmations: Confirmation[]
  handoffs: Handoff[]
  chatContext: { product_id: string; movement?: Movement } | null
  reportCases: Record<string, string>
}
const empty = (role: Role): State => ({
  role,
  signedIn: false,
  username: '',
  busy: false,
  error: '',
  retryable: false,
  acknowledgedTurn: null,
  cards: [],
  release: '',
  movements: null,
  selected: '',
  conversation: null,
  conversationHistory: [],
  confirmations: [],
  handoffs: [],
  chatContext: null,
  reportCases: {},
})
export class Demo {
  private state = empty('customer')
  private listeners = new Set<() => void>()
  private api: Api
  private controller: AbortController | null = null
  private epoch = 0
  private retryOperation: (() => Promise<void>) | null = null
  constructor(transport?: typeof fetch) {
    this.api = new Api(() => this.reset('session_expired'), transport)
  }
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
  snapshot = () => this.state
  private patch(value: Partial<State>) {
    this.state = { ...this.state, ...value }
    if (value.conversation) {
      const current = value.conversation
      const history = this.state.conversationHistory
      this.state.conversationHistory = history.some(c => c.conversation_id === current.conversation_id)
        ? history.map(c => c.conversation_id === current.conversation_id ? current : c)
        : [current, ...history]
    }
    this.listeners.forEach((listener) => listener())
  }
  private reset(error = '') {
    this.epoch++
    this.controller?.abort()
    this.api.clear()
    this.retryOperation = null
    this.state = { ...empty(this.state.role), error }
    this.listeners.forEach((listener) => listener())
  }
  setRole(role: Role) {
    if (!this.state.signedIn && !this.state.busy) {
      this.reset()
      this.patch({ role })
    }
  }
  private async run(operation: () => Promise<void>, retryable = false) {
    if (this.state.busy || this.retryOperation) return
    const epoch = this.epoch
    this.controller = new AbortController()
    this.patch({ busy: true, error: '', retryable: false })
    try {
      await operation()
    } catch (error) {
      if (epoch !== this.epoch) return
      const aborted =
        error instanceof DOMException && error.name === 'AbortError'
      const code = aborted
        ? 'cancelled_request'
        : error instanceof ApiError
          ? error.code
          : 'invalid_response'
      // A lost response or local cancellation may have committed. Keep the SAME command for explicit replay.
      const uncertain =
        retryable &&
        (aborted ||
          (error instanceof ApiError &&
            (error.status === 0 || error.status >= 500)))
      if (uncertain) this.retryOperation = operation
      this.patch({ error: code, retryable: uncertain })
    } finally {
      if (epoch === this.epoch) this.patch({ busy: false })
    }
  }
  cancelRequest() {
    this.controller?.abort()
  }
  retry() {
    const operation = this.retryOperation
    this.retryOperation = null
    if (operation) return this.run(operation, true)
  }
  private request<T>(
    path: string,
    method: 'GET' | 'POST' = 'GET',
    body?: unknown,
    key?: string,
  ) {
    return this.api.request<T>(path, {
      method,
      body,
      key,
      signal: this.controller?.signal,
    })
  }
  login(role: Role, username: string, password: string) {
    if (this.state.signedIn || this.state.busy || this.retryOperation ||
        role !== this.state.role) return
    // A new login owns a new UI epoch, including same-role account changes.
    this.epoch++
    return this.run(async () => {
      const result = await this.request<{ access_token: string }>(
        role === 'customer' ? '/auth/login' : '/agent/auth/login',
        'POST',
        { username, password },
      )
      if (typeof result.access_token !== 'string' || !result.access_token)
        throw new ApiError(502, 'invalid_response')
      this.api.authenticate(result.access_token)
      this.patch({ role, signedIn: true, username })
      await this.refreshData()
    })
  }
  async logout() {
    // Start server revocation before aborting pending work; clear UI and credentials immediately.
    const path =
      this.state.role === 'customer' ? '/auth/logout' : '/agent/auth/logout'
    const revocation = this.api.request(path, { method: 'POST', body: {} })
    this.reset()
    const logoutEpoch = this.epoch
    try {
      await revocation
    } catch (error) {
      if (logoutEpoch === this.epoch &&
          !(error instanceof DOMException && error.name === 'AbortError'))
        this.patch({ error: 'logout_unconfirmed' })
    }
  }
  private async refreshData() {
    if (this.state.role === 'customer') {
      await this.request('/me')
      const cards = await this.request<Cards>('/me/cards')
      if (!validCards(cards)) throw new ApiError(502, 'invalid_response')
      this.patch({ cards: cards.cards, release: cards.release_id })
    }
    const handoffs: Handoff[] = []
    let offset: number | null = 0
    while (offset !== null) {
      const result: { handoffs: Handoff[]; next_offset: number | null } =
        await this.request(
          `${this.state.role === 'customer' ? '/me' : '/agent'}/handoffs?limit=100&offset=${offset}`,
        )
      if (!Array.isArray(result.handoffs) || !result.handoffs.every(validHandoff) || !(result.next_offset === null || Number.isInteger(result.next_offset))) throw new ApiError(502, 'invalid_response')
      handoffs.push(...result.handoffs)
      if (
        result.next_offset !== null &&
        (result.next_offset <= offset || result.next_offset > 10000)
      )
        throw new ApiError(502, 'invalid_response')
      offset = result.next_offset
    }
    this.patch({ handoffs })
    if (this.state.conversation && this.state.role === 'customer')
      await this.reconcileConversation()
  }
  refresh() {
    return this.run(() => this.refreshData())
  }
  selectCard(id: string, cursor?: string) {
    return this.run(async () => {
      this.patch({
        selected: id,
        movements: cursor ? this.state.movements : null,
      })
      const result = await this.request<Movements>(
        `/me/cards/${segment(id)}/movements?limit=20${cursor ? `&cursor=${segment(cursor)}` : ''}`,
      )
      if (!validMovements(result)) throw new ApiError(502, 'invalid_response')
      this.patch({
        movements:
          cursor && this.state.movements
            ? {
                ...result,
                movements: [
                  ...this.state.movements.movements,
                  ...result.movements,
                ],
              }
            : result,
      })
    })
  }
  prepare(
    id: string,
    action: Action,
    transaction?: { transaction_id: string; process_date: string },
  ) {
    const key = commandKey()
    return this.run(async () => {
      const result = await this.request<Confirmation>(
        `/me/cards/${segment(id)}/actions`,
        'POST',
        { action, ...transaction },
        key,
      )
      this.saveConfirmation(result, undefined, {product_id: id, action, ...transaction})
    }, true)
  }
  private saveConfirmation(
    result: Confirmation,
    expectedId?: string,
    expectedCommand?: Confirmation['command'],
  ) {
    if (!validConfirmation(result) ||
        (expectedId !== undefined && result.confirmation_id !== expectedId) ||
        (expectedCommand !== undefined &&
          (result.command.product_id !== expectedCommand.product_id ||
           result.command.action !== expectedCommand.action ||
           (result.command.transaction_id ?? null) !== (expectedCommand.transaction_id ?? null) ||
           (result.command.process_date ?? null) !== (expectedCommand.process_date ?? null))))
      throw new ApiError(502, 'invalid_response')
    if (result.status === 'executed' && !verifiedReceipt(result))
      throw new ApiError(502, 'invalid_receipt')
    this.patch({
      confirmations: [
        ...this.state.confirmations.filter(
          (c) => c.confirmation_id !== result.confirmation_id,
        ),
        result,
      ],
    })
  }
  async reviewConfirmation(id: string): Promise<Confirmation | undefined> {
    const expected = this.state.confirmations.find(c => c.confirmation_id === id)?.command
    if (!expected) return
    let reviewed: Confirmation | undefined
    await this.run(async () => {
      const result = await this.request<Confirmation>(`/me/action-confirmations/${segment(id)}`)
      this.saveConfirmation(result, id, expected)
      if (result.status === 'executed') await this.refreshData()
      if (result.status === 'pending') {
        if (!(Date.parse(result.expires_at) > Date.now()))
          throw new ApiError(409, 'http_409')
        reviewed = result
      }
    })
    return reviewed
  }
  confirmation(id: string, operation: 'confirm' | 'cancel' | 'refresh') {
    const expected = this.state.confirmations.find(c => c.confirmation_id === id)?.command
    if (!expected) return
    return this.run(async () => {
      const result = await this.request<Confirmation>(
        `/me/action-confirmations/${segment(id)}${operation === 'refresh' ? '' : `/${operation}`}`,
        operation === 'refresh' ? 'GET' : 'POST',
        operation === 'refresh' ? undefined : {},
      )
      this.saveConfirmation(result, id, expected)
      if (result.status === 'executed') await this.refreshData()
    }, operation !== 'refresh')
  }
  startConversation(locale: Locale) {
    const key = commandKey()
    return this.run(async () => {
      const result = await this.request<Conversation>('/me/conversations', 'POST', { language: locale }, key)
      if (!validConversation(result)) throw new ApiError(502, 'invalid_response')
      this.patch({ conversation: result })
    }, true)
  }
  setChatContext(productId: string, movement?: Movement) {
    if (this.state.busy || this.state.retryable) return
    if (productId === '') { this.patch({ chatContext: null }); return }
    if (!this.state.cards.some(c => c.product_id === productId)) return
    if (movement && (this.state.selected !== productId || !this.state.movements?.movements.some(m => m.transaction_id === movement.transaction_id && m.process_date === movement.process_date))) return
    this.patch({ chatContext: { product_id: productId, ...(movement ? { movement } : {}) } })
  }
  async guidedRequest(action: 'pause' | 'block' | 'unrecognized-charge', locale: Locale) {
    if (this.state.busy || this.state.retryable || !this.state.signedIn) return
    const epoch = this.epoch
    const context = this.state.chatContext
    if (!context || !this.state.cards.some(c => c.product_id === context.product_id)) return
    if (!this.state.conversation) {
      await this.startConversation(locale)
      if (this.state.error) return
    }
    const conversation = this.state.conversation
    if (epoch !== this.epoch || !conversation || this.state.retryable) return
    if (conversation.adapter.mode === 'disabled' || (conversation.adapter.mode === 'stub' && action !== 'pause')) {
      this.patch({ error: 'unsupported_chat_action' })
      return
    }
    const copy = workflowCopy[locale]
    if (action === 'unrecognized-charge' && !context.movement) return
    const message = conversation.adapter.mode === 'stub'
      ? `/pause ${context.product_id}`
      : action === 'unrecognized-charge'
        ? `${copy.chargePrompt}\n${copy.cardContext}: ${context.product_id}\n${copy.transaction}: ${context.movement!.transaction_id}\n${copy.processDate}: ${context.movement!.process_date}`
        : `${action === 'pause' ? copy.pause : copy.block}. ${copy.cardContext}: ${context.product_id}. ${copy.selectionNote}`
    await this.turn(message, locale, context.product_id)
  }
  async requestConversationHandoff(locale: Locale) {
    if (this.state.busy || this.state.retryable || !this.state.signedIn) return
    const epoch = this.epoch
    if (!this.state.conversation) {
      await this.startConversation(locale)
      if (this.state.error) return
    }
    if (epoch !== this.epoch || !this.state.conversation || this.state.retryable) return
    if (this.state.conversation.adapter.mode === 'disabled') {
      this.patch({ error: 'unsupported_chat_action' })
      return
    }
    await this.turn(this.state.conversation.adapter.mode === 'stub' ? '/handoff' : workflowCopy[locale].handoffPrompt, locale)
  }
  reportCharge(confirmationId: string, locale: Locale) {
    const confirmation = this.state.confirmations.find(c => c.confirmation_id === confirmationId)
    const receipt = confirmation && verifiedReceipt(confirmation)
    if (!receipt || receipt.action !== 'unrecognized-charge' || !validChargeIdentity(confirmation.command) || this.state.reportCases[receipt.action_id]) return
    const copy = workflowCopy[locale]
    const conversation = this.state.conversation?.events.some(e => e.trust === 'backend' && e.confirmation_id === confirmationId) ? this.state.conversation.conversation_id : null
    const context = [
      `${copy.transaction}: ${confirmation.command.transaction_id}`,
      `${copy.processDate}: ${confirmation.command.process_date}`,
      `${copy.request}: ${receipt.request_id}`,
      ...(conversation ? [`${copy.conversation}: ${conversation}`] : []),
    ].join('\n')
    const payload = { reason: 'card_support', severity: 'low', required_specialty: null, minimum_experience: 'Junior', language: locale, summary: copy.supportSummary, context, unresolved_questions: [copy.question], product_id: receipt.product_id }
    const key = commandKey()
    return this.run(async () => {
      const result = await this.request<Handoff>('/me/handoffs', 'POST', payload, key)
      if (!validHandoff(result) || !result.persisted ||
          result.model_context.context !== context ||
          !result.verified_evidence.actions.some(({ receipt: saved }) =>
            Object.entries(receipt).every(([field, value]) => saved[field as keyof typeof saved] === value)))
        throw new ApiError(502, 'invalid_response')
      this.patch({ reportCases: { ...this.state.reportCases, [receipt.action_id]: result.handoff_id } })
      await this.refreshData()
    }, true)
  }
  newChat() {
    if (!this.state.busy && !this.state.retryable) this.patch({ conversation: null, chatContext: null })
  }
  openConversation(id: string) {
    return this.run(async () => {
      const result = await this.request<Conversation>(`/me/conversations/${segment(id)}`)
      if (!validConversation(result) || result.conversation_id !== id) throw new ApiError(502, 'invalid_response')
      this.patch({ conversation: result, chatContext: null })
      await this.reconcileConversation()
    })
  }
  async turn(message: string, locale: Locale, selectedProductId: string | null = null): Promise<boolean> {
    const id = this.state.conversation?.conversation_id
    if (!id || !message.trim() || message.length > 2000 || this.state.busy || this.retryOperation) return false
    if (selectedProductId !== null && !this.state.cards.some(card => card.product_id === selectedProductId)) {
      await this.run(async () => { throw new ApiError(422, 'http_422') })
      return false
    }
    const epoch = this.epoch
    let acknowledged = false
    const key = commandKey()
    const body = { message, language: locale, selected_product_id: selectedProductId }
    await this.run(async () => {
      const result = await this.request<Conversation>(
        `/me/conversations/${segment(id)}/turns`,
        'POST',
        body,
        key,
      )
      if (!validConversation(result) || result.conversation_id !== id) throw new ApiError(502, 'invalid_response')
      acknowledged = true
      this.patch({
        acknowledgedTurn: this.state.acknowledgedTurn?.key === key ? this.state.acknowledgedTurn : { key, message },
        conversation: {
          ...result,
          events: mergeEvents(
            this.state.conversation?.events ?? [],
            result.events,
          ),
        },
      })
      await this.refreshData()
    }, true)
    // Only a bound response acknowledges the text. Uncertain replay may still be rejected.
    return epoch === this.epoch && acknowledged
  }
  private async reconcileConversation() {
    const id = this.state.conversation?.conversation_id
    if (!id) return
    let after: number | null = 0
    while (after !== null) {
      const page: Conversation = await this.request<Conversation>(
        `/me/conversations/${segment(id)}?after=${after}&limit=100`,
      )
      if (!validConversation(page) || page.conversation_id !== id) throw new ApiError(502, 'invalid_response')
      this.patch({
        conversation: {
          ...page,
          events: mergeEvents(
            this.state.conversation?.events ?? [],
            page.events,
          ),
        },
      })
      if (page.next_after === null) break
      if (page.next_after <= after) throw new ApiError(502, 'invalid_response')
      after = page.next_after
    }
    const ids = new Set(
      this.state.conversation?.events
        .filter((e) => e.trust === 'backend' && e.confirmation_id)
        .map((e) => e.confirmation_id as string),
    )
    for (const confirmationId of ids)
      this.saveConfirmation(
        await this.request<Confirmation>(
          `/me/action-confirmations/${segment(confirmationId)}`,
        ),
        confirmationId,
        this.state.confirmations.find(c => c.confirmation_id === confirmationId)?.command,
      )
  }
  handoff(summary: string, locale: Locale) {
    const key = commandKey()
    return this.run(async () => {
      await this.request<Handoff>(
        '/me/handoffs',
        'POST',
        {
          reason: 'card_support',
          severity: 'low',
          required_specialty: null,
          minimum_experience: 'Junior',
          language: locale,
          summary,
        },
        key,
      )
      await this.refreshData()
    }, true)
  }
  transition(id: string, operation: 'accept' | 'resolve' | 'cancel') {
    return this.run(async () => {
      const prefix = this.state.role === 'customer' ? '/me' : '/agent'
      await this.request<Handoff>(
        `${prefix}/handoffs/${segment(id)}/${operation}`,
        'POST',
        {},
      )
      await this.refreshData()
    }, true)
  }
}
