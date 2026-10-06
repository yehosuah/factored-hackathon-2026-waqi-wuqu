import { messages, translateStatus } from '../src/i18n.ts'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Api } from '../src/api.ts'
import { Demo } from '../src/demo.ts'
import {
  availableActions,
  mergeEvents,
  verifiedReceipt,
  validHandoff, validChargeIdentity,
  validAdapter,
  validConversation,
  adapterKind,
  conversationRead,
  validCards,
  cardLabel,
  validMovements,
  type Confirmation,
  type ConversationEvent,
} from '../src/contracts.ts'
import { money, sourceDate, sourceLabel } from '../src/workflow-copy.ts'
const id = 'a'.repeat(32)
const pending: Confirmation = {
  confirmation_id: id,
  command: { product_id: 'CARD-1', action: 'pause' },
  status: 'pending',
  simulated: true,
  verified: false,
  expires_at: '2026-10-06T00:00:00Z',
}
const executed: Confirmation = {
  ...pending,
  status: 'executed',
  verified: true,
  evidence: {
    action_id: 'b'.repeat(32),
    product_id: 'CARD-1',
    action: 'pause',
    status: 'succeeded',
    outcome: 'state_change_verified',
    simulator_state: 'PAUSED',
    simulated: true,
    source_kind: 'team_synthetic',
    release_id: 'synthetic-1',
  },
}
type Call = { path: string; options: RequestInit }
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
function harness(
  handler?: (call: Call) => Response | Promise<Response> | undefined,
) {
  const calls: Call[] = []
  const transport = (async (
    input: RequestInfo | URL,
    options: RequestInit = {},
  ) => {
    const call = { path: String(input), options }
    calls.push(call)
    const response = handler?.(call)
    if (response) return response
    if (call.path.endsWith('/auth/login'))
      return json({
        access_token: call.path.includes('/agent/')
          ? 'agent-opaque'
          : 'customer-opaque',
      })
    if (call.path === '/api/me') return json({ username: 'customer' })
    if (call.path === '/api/me/cards')
      return json({
        cards: [{ product_id: 'CARD-1', product_type: 'Tarjeta Crédito', last_four: '4242', currency: 'USD', current_balance: '125.50', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }],
        release_id: 'synthetic-1',
      })
    if (call.path.includes('/handoffs'))
      return json({ handoffs: [], next_offset: null })
    return json({})
  }) as typeof fetch
  return { demo: new Demo(transport), calls, transport }
}
const body = (call: Call) =>
  JSON.parse(String(call.options.body)) as Record<string, unknown>
const headers = (call: Call) => call.options.headers as Record<string, string>
test('session history can reopen server conversations and is removed on account change', async () => {
  let number = 0
  const conversation = (conversation_id: string) => ({ conversation_id, adapter: { provider: 'stub', mode: 'stub', version: '1' }, events: [], next_after: null, last_sequence: 0 })
  const h = harness(call => {
    if (call.path === '/api/me/conversations') return json(conversation(String(++number).repeat(32)))
    if (call.path.startsWith('/api/me/conversations/')) return json(conversation(call.path.split('/')[4].split('?')[0]))
  })
  await h.demo.login('customer', 'first', 'private-test-value')
  await h.demo.startConversation('es')
  const first = h.demo.snapshot().conversation!.conversation_id
  h.demo.newChat()
  assert.equal(h.demo.snapshot().conversation, null)
  await h.demo.startConversation('pt')
  assert.equal(h.demo.snapshot().conversationHistory.length, 2)
  await h.demo.openConversation(first)
  assert.equal(h.demo.snapshot().conversation!.conversation_id, first)
  assert.equal(h.demo.snapshot().conversationHistory.length, 2)
  await h.demo.logout()
  assert.deepEqual(h.demo.snapshot().conversationHistory, [])
  await h.demo.login('customer', 'second', 'private-test-value')
  assert.deepEqual(h.demo.snapshot().conversationHistory, [])
})
test('same-origin requests use opaque bearer, omit cookies, and expire on 401', async () => {
  let expired = 0
  const h = harness(() => json({}, 401))
  const api = new Api(() => expired++, h.transport)
  api.authenticate('opaque-session')
  await assert.rejects(api.request('/me'), /http_401/)
  assert.equal(expired, 1)
  assert.equal(h.calls[0].path, '/api/me')
  assert.equal(headers(h.calls[0]).Authorization, 'Bearer opaque-session')
  assert.equal(h.calls[0].options.credentials, 'omit')
  await assert.rejects(api.request('/me'), /http_401/)
  assert.equal(headers(h.calls[1]).Authorization, undefined)
})
test('pause only prepares; explicit confirm returns typed receipt and refreshes cards', async () => {
  const h = harness((c) =>
    c.path.endsWith('/actions')
      ? json(pending)
      : c.path.endsWith('/confirm')
        ? json(executed)
        : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.prepare('CARD-1', 'pause')
  assert.equal(h.demo.snapshot().confirmations[0].status, 'pending')
  assert.equal(
    h.calls.some((c) => c.path.endsWith('/confirm')),
    false,
  )
  assert.deepEqual(body(h.calls.find((c) => c.path.endsWith('/actions'))!), {
    action: 'pause',
  })
  const before = h.calls.filter((c) => c.path === '/api/me/cards').length
  await h.demo.confirmation(id, 'confirm')
  assert.deepEqual(body(h.calls.find((c) => c.path.endsWith('/confirm'))!), {})
  assert.ok(verifiedReceipt(h.demo.snapshot().confirmations[0]))
  assert.equal(
    h.calls.filter((c) => c.path === '/api/me/cards').length,
    before + 1,
  )
})
test('lost prepare response locks new commands and explicit retry preserves key and payload', async () => {
  let attempts = 0
  const h = harness((c) => {
    if (c.path.endsWith('/actions')) {
      if (++attempts === 1) throw new TypeError('lost response')
      return json(pending)
    }
  })
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.prepare('CARD-1', 'pause')
  assert.equal(h.demo.snapshot().retryable, true)
  await h.demo.prepare('CARD-1', 'block')
  assert.equal(attempts, 1)
  await h.demo.retry()
  const commands = h.calls.filter((c) => c.path.endsWith('/actions'))
  assert.equal(commands.length, 2)
  assert.equal(
    headers(commands[0])['Idempotency-Key'],
    headers(commands[1])['Idempotency-Key'],
  )
  assert.equal(commands[0].options.body, commands[1].options.body)
  assert.match(
    headers(commands[0])['Idempotency-Key'],
    /^[A-Za-z0-9_.:-]{1,100}$/,
  )
  assert.equal(h.demo.snapshot().retryable, false)
})
test('401 clears every customer resource, retry and bearer before agent login', async () => {
  let fail = false
  const h = harness((c) =>
    fail && c.path === '/api/me' ? json({}, 401) : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  fail = true
  await h.demo.refresh()
  assert.deepEqual(h.demo.snapshot().cards, [])
  assert.equal(h.demo.snapshot().signedIn, false)
  assert.equal(h.demo.snapshot().conversation, null)
  assert.equal(h.demo.snapshot().selected, '')
  assert.equal(h.demo.snapshot().error, 'session_expired')
  h.demo.setRole('agent')
  await h.demo.login('agent', 'human', 'private-test-value')
  const login = h.calls.find((c) => c.path === '/api/agent/auth/login')!
  assert.equal(headers(login).Authorization, undefined)
  assert.equal(headers(h.calls.at(-1)!).Authorization, 'Bearer agent-opaque')
  assert.deepEqual(h.demo.snapshot().cards, [])
})
test('logout revokes correct principal and rejects a late response', async () => {
  let release: ((response: Response) => void) | undefined
  let delay = false
  const h = harness((c) =>
    delay && c.path === '/api/me/cards'
      ? new Promise<Response>((resolve) => {
          release = resolve
        })
      : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  delay = true
  const refresh = h.demo.refresh()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await h.demo.logout()
  assert.equal(
    headers(h.calls.find((c) => c.path === '/api/auth/logout')!).Authorization,
    'Bearer customer-opaque',
  )
  release!(json({ cards: [{ product_id: 'OLD-CUSTOMER' }], release_id: 'old' }))
  await refresh
  assert.equal(h.demo.snapshot().signedIn, false)
  assert.deepEqual(h.demo.snapshot().cards, [])
  h.demo.setRole('agent')
  delay = false
  await h.demo.login('agent', 'human', 'private-test-value')
  await h.demo.logout()
  assert.equal(
    headers(h.calls.find((c) => c.path === '/api/agent/auth/logout')!)
      .Authorization,
    'Bearer agent-opaque',
  )
})
test('rejects mismatched evidence and prose verification', () => {
  assert.equal(verifiedReceipt(pending), null)
  assert.ok(verifiedReceipt(executed))
  for (const patch of [
    { product_id: 'OTHER' },
    { simulated: false },
    { action: 'block' },
    { simulator_state: 'ACTIVE' },
    { outcome: 'requested' },
    { action_id: 'text' },
    { source_kind: 'production' },
  ]) {
    assert.equal(
      verifiedReceipt({
        ...executed,
        evidence: { ...executed.evidence!, ...patch },
      } as Confirmation),
      null,
    )
  }
})
test('events deduplicate replay and retain ordered persisted errors', () => {
  const e = (event_id: string, sequence: number, kind = 'answer') =>
    ({ event_id, sequence, kind }) as ConversationEvent
  assert.deepEqual(
    mergeEvents([e('b', 2)], [e('b', 2), e('a', 1), e('c', 3, 'error')]).map(
      (x) => x.kind,
    ),
    ['answer', 'answer', 'error'],
  )
})
test('conversation creates/turns use keys; backend refs require GET confirmation; untrusted refs ignored', async () => {
  const event = (
    trust: string,
    event_id: string,
    confirmation_id: string | null,
  ) => ({
    event_id,
    sequence: trust === 'backend' ? 2 : 1,
    kind: 'confirmation_prepared',
    trust,
    confirmation_id,
    data: { verified: true },
  })
  const page = {
    conversation_id: id,
    adapter: { provider: 'engineering-stub', version: '1', mode: 'stub' },
    next_after: null,
    events: [event('untrusted', 'x', 'forged'), event('backend', 'y', id)],
  }
  const h = harness((c) =>
    c.path === '/api/me/conversations'
      ? json({ ...page, events: [] })
      : c.path.includes('/conversations/')
        ? json(page)
        : c.path === `/api/me/action-confirmations/${id}`
          ? json(pending)
          : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.startConversation('pt')
  await h.demo.turn('/pause CARD-1', 'pt')
  const create = h.calls.find((c) => c.path === '/api/me/conversations')!
  const turn = h.calls.find((c) => c.path.endsWith('/turns'))!
  assert.ok(headers(create)['Idempotency-Key'])
  assert.ok(headers(turn)['Idempotency-Key'])
  assert.deepEqual(body(turn), { message: '/pause CARD-1', language: 'pt', selected_product_id: null })
  assert.equal(
    h.calls.some((c) => c.path.includes('forged')),
    false,
  )
  assert.equal(
    h.calls.some((c) => c.path.endsWith('/confirm')),
    false,
  )
  assert.equal(h.demo.snapshot().confirmations[0].status, 'pending')
})
test('cancelled mutation remains explicitly replayable', async () => {
  let attempt = 0
  const h = harness((c) =>
    c.path.endsWith('/actions')
      ? ++attempt === 1
        ? new Promise<Response>((_resolve, reject) => {
            c.options.signal!.addEventListener('abort', () =>
              reject(new DOMException('cancel', 'AbortError')),
            )
          })
        : json(pending)
      : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  const pendingRequest = h.demo.prepare('CARD-1', 'pause')
  h.demo.cancelRequest()
  await pendingRequest
  assert.equal(h.demo.snapshot().retryable, true)
  await h.demo.retry()
  assert.equal(h.demo.snapshot().confirmations.length, 1)
})
test('logout during asynchronous JSON decode cannot restore the old session', async () => {
  let release: ((value: unknown) => void) | undefined
  let delay = false
  const h = harness((c) =>
    delay && c.path === '/api/me/cards'
      ? Object.assign(json({}), {
          json: () =>
            new Promise((resolve) => {
              release = resolve
            }),
        })
      : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  delay = true
  const refresh = h.demo.refresh()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await h.demo.logout()
  release!({ cards: [{ product_id: 'OLD-CUSTOMER' }], release_id: 'old' })
  await refresh
  assert.deepEqual(h.demo.snapshot().cards, [])
})
test('role cannot switch an active principal or submit an agent login with a customer bearer', async () => {
  const h = harness()
  await h.demo.login('customer', 'one', 'private-test-value')
  h.demo.setRole('agent')
  await h.demo.login('agent', 'human', 'private-test-value')
  assert.equal(h.demo.snapshot().role, 'customer')
  assert.equal(
    h.calls.some((c) => c.path === '/api/agent/auth/login'),
    false,
  )
})
test('cancel confirmation uses the saved identifier and does not execute the command', async () => {
  const h = harness((c) =>
    c.path.endsWith('/actions')
      ? json(pending)
      : c.path.endsWith('/cancel')
        ? json({ ...pending, status: 'cancelled' })
        : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.prepare('CARD-1', 'pause')
  await h.demo.confirmation(id, 'cancel')
  assert.equal(h.demo.snapshot().confirmations[0].status, 'cancelled')
  assert.equal(
    h.calls.some((c) => c.path.endsWith('/confirm')),
    false,
  )
})
test('handoff triage carries no principal assertion and create replay keeps the key', async () => {
  let attempts = 0
  const h = harness((c) =>
    c.path === '/api/me/handoffs' && c.options.method === 'POST'
      ? ++attempts === 1
        ? json({}, 503)
        : json({ handoff_id: id })
      : undefined,
  )
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.handoff('Preciso de ajuda', 'pt')
  await h.demo.retry()
  const creates = h.calls.filter(
    (c) => c.path === '/api/me/handoffs' && c.options.method === 'POST',
  )
  assert.deepEqual(body(creates[0]), {
    reason: 'card_support',
    severity: 'low',
    required_specialty: null,
    minimum_experience: 'Junior',
    language: 'pt',
    summary: 'Preciso de ajuda',
  })
  assert.equal(
    headers(creates[0])['Idempotency-Key'],
    headers(creates[1])['Idempotency-Key'],
  )
})
test('default transport invokes global fetch without binding it to the API instance', async () => {
  const original = globalThis.fetch
  let called = false
  globalThis.fetch = function (this: unknown) {
    assert.equal(this, undefined)
    called = true
    return Promise.resolve(json({ ok: true }))
  } as typeof fetch
  try {
    const api = new Api(() => {})
    await api.request('/health/ready')
    assert.equal(called, true)
  } finally {
    globalThis.fetch = original
  }
})
test('malformed successful responses become visible errors instead of crashing the account UI', async () => {
  const h = harness(c => c.path === '/api/me/cards' ? json({}) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  assert.equal(h.demo.snapshot().error, 'invalid_response')
  assert.deepEqual(h.demo.snapshot().cards, [])
})
test('card controls offer relevant transitions, with backend retaining final authorization', () => {
  assert.deepEqual(availableActions('ACTIVE'), ['pause', 'block', 'replacement'])
  assert.deepEqual(availableActions('PAUSED'), ['reactivate', 'block', 'replacement'])
  assert.deepEqual(availableActions('PENDING_ACTIVATION'), ['activate', 'block', 'replacement'])
  assert.deepEqual(availableActions('BLOCKED'), ['replacement'])
  assert.deepEqual(availableActions('CLOSED'), [])
})

test('logout failure remains visible after local credentials are cleared', async () => {
  const h = harness((c) => c.path.endsWith('/logout') ? json({}, 503) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.logout()
  assert.equal(h.demo.snapshot().signedIn, false)
  assert.equal(h.demo.snapshot().error, 'logout_unconfirmed')
  assert.deepEqual(h.demo.snapshot().cards, [])
})

test('late logout failure cannot annotate a new principal session', async () => {
  let release!: (response: Response) => void
  const h = harness((c) => c.path.endsWith('/logout') ? new Promise<Response>((resolve) => { release = resolve }) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  const logout = h.demo.logout()
  h.demo.setRole('agent')
  await h.demo.login('agent', 'human', 'private-test-value')
  release(json({}, 503))
  await logout
  assert.equal(h.demo.snapshot().signedIn, true)
  assert.equal(h.demo.snapshot().role, 'agent')
  assert.equal(h.demo.snapshot().error, '')
})

test('late logout failure cannot annotate a new customer session', async () => {
  let release!: (response: Response) => void
  const h = harness((c) => c.path.endsWith('/logout') ? new Promise<Response>((resolve) => { release = resolve }) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  const logout = h.demo.logout()
  await h.demo.login('customer', 'two', 'private-test-value')
  release(json({}, 503))
  await logout
  assert.equal(h.demo.snapshot().signedIn, true)
  assert.equal(h.demo.snapshot().username, 'two')
  assert.equal(h.demo.snapshot().error, '')
})

test('review reads current backend status and never enables a cancelled cached command', async () => {
  const h = harness(c => c.path.endsWith('/actions') ? json(pending) : c.path === `/api/me/action-confirmations/${id}` ? json({...pending,status:'cancelled'}) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.prepare('CARD-1','pause')
  assert.equal(await h.demo.reviewConfirmation(id), undefined)
  assert.equal(h.demo.snapshot().confirmations[0].status,'cancelled')
  assert.equal(h.calls.filter(c => c.path === `/api/me/action-confirmations/${id}` && c.options.method === 'GET').length,1)
  assert.equal(h.calls.some(c => c.path.endsWith('/confirm')),false)
})

test('confirm cancel and refresh reject a different response confirmation identifier', async () => {
  for (const operation of ['confirm','cancel','refresh'] as const) {
    const h = harness(c => c.path.endsWith('/actions') ? json(pending) : c.path.includes('/action-confirmations/') ? json({...executed,confirmation_id:'c'.repeat(32)}) : undefined)
    await h.demo.login('customer','one','private-test-value')
    await h.demo.prepare('CARD-1','pause')
    await h.demo.confirmation(id,operation)
    assert.equal(h.demo.snapshot().error,'invalid_response')
    assert.deepEqual(h.demo.snapshot().confirmations,[pending])
  }
})

test('confirmation responses must match the command the customer reviewed', async () => {
  const swapped = {...executed,command:{product_id:'CARD-2',action:'pause' as const},evidence:{...executed.evidence!,product_id:'CARD-2'}}
  assert.ok(verifiedReceipt(swapped))
  const h = harness(c => c.path.endsWith('/actions') ? json(pending) : c.path.endsWith('/confirm') ? json(swapped) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.prepare('CARD-1','pause')
  await h.demo.confirmation(id,'confirm')
  assert.equal(h.demo.snapshot().error,'invalid_response')
  assert.deepEqual(h.demo.snapshot().confirmations,[pending])
})

test('review returns only a fresh pending confirmation after the required GET', async () => {
  const fresh = {...pending,expires_at:new Date(Date.now() + 86400000).toISOString()}
  const h = harness(c => c.path.endsWith('/actions') ? json(pending) : c.path === `/api/me/action-confirmations/${id}` ? json(fresh) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.prepare('CARD-1','pause')
  assert.deepEqual(await h.demo.reviewConfirmation(id),fresh)
  assert.equal(h.calls.at(-1)!.options.method,'GET')
})

test('an expired pending response cannot enable confirmation review', async () => {
  const h = harness(c => c.path.endsWith('/actions') ? json(pending) : c.path === `/api/me/action-confirmations/${id}` ? json({...pending,expires_at:'2000-01-01T00:00:00Z'}) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.prepare('CARD-1','pause')
  assert.equal(await h.demo.reviewConfirmation(id),undefined)
  assert.equal(h.demo.snapshot().error,'http_409')
  assert.equal(h.calls.some(c => c.path.endsWith('/confirm')),false)
})

test('prepare rejects a response for a different requested card command', async () => {
  const h = harness(c => c.path.endsWith('/actions') ? json({...pending,command:{product_id:'CARD-2',action:'block'}}) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.prepare('CARD-1','pause')
  assert.equal(h.demo.snapshot().error,'invalid_response')
  assert.deepEqual(h.demo.snapshot().confirmations,[])
})

test('turn and history responses cannot replace the requested conversation', async () => {
  const active = {conversation_id:id,adapter:{provider:'engineering-stub',version:'1',mode:'stub'},events:[],next_after:null,last_sequence:0}
  for (const mismatch of ['turn','history']) {
    const h = harness(c => c.path === '/api/me/conversations' ? json(active) : c.path.includes('/conversations/') ? json({...active,conversation_id: mismatch === 'history' || c.path.endsWith('/turns') ? 'd'.repeat(32) : id}) : undefined)
    await h.demo.login('customer','one','private-test-value')
    await h.demo.startConversation('es')
    if (mismatch === 'turn') await h.demo.turn('/cards','es')
    else await h.demo.refresh()
    assert.equal(h.demo.snapshot().error,'invalid_response')
    assert.equal(h.demo.snapshot().conversation?.conversation_id,id)
    assert.equal(h.calls.some(c => c.path.includes('d'.repeat(32))),false)
  }
})

test('a successful turn downloads conversation history only once', async () => {
  const active = {conversation_id:id,adapter:{provider:'engineering-stub',version:'1',mode:'stub'},events:[],next_after:null,last_sequence:0}
  const h = harness(c => c.path === '/api/me/conversations' || c.path.includes('/conversations/') ? json(active) : undefined)
  await h.demo.login('customer','one','private-test-value')
  await h.demo.startConversation('es')
  await h.demo.turn('/cards','es')
  assert.equal(h.calls.filter(c => c.path.includes('/conversations/') && c.options.method === 'GET').length,1)
})

test('malformed handoff render fields become visible errors before reaching React', async () => {
  const valid = {handoff_id:id,status:'assigned',reason:'card_support',severity:'low',assigned_agent_id:'AGENT-1',queue:null,release_id:'synthetic-1',triage:{language:'es'},model_context:{summary:'Synthetic case',context:'',unresolved_questions:[]},verified_evidence:{source:'backend',release_id:'synthetic-1',actions:[]},persisted:true}
  assert.equal(validHandoff(valid),true)
  const variants = [{...valid,assigned_agent_id:{}},{...valid,queue:{}},{...valid,model_context:{...valid.model_context,summary:{}}},{...valid,model_context:{...valid.model_context,context:{}}},{...valid,model_context:{...valid.model_context,unresolved_questions:{}}},{...valid,model_context:{...valid.model_context,unresolved_questions:[{}]}}]
  for (const malformed of variants) {
    assert.equal(validHandoff(malformed),false)
    const h = harness(c => c.path.includes('/handoffs') ? json({handoffs:[malformed],next_offset:null}) : undefined)
    await h.demo.login('customer','one','private-test-value')
    assert.equal(h.demo.snapshot().error,'invalid_response')
    assert.deepEqual(h.demo.snapshot().handoffs,[])
  }
})

test('handoff receipts reject non-string render fields even when the command self-matches', () => {
  const valid = {handoff_id:id,status:'assigned',reason:'card_support',severity:'low',assigned_agent_id:'AGENT-1',queue:null,release_id:'synthetic-1',triage:{language:'es'},model_context:{summary:'Synthetic case'},verified_evidence:{source:'backend',release_id:'synthetic-1',actions:[{receipt:executed.evidence,committed_at:'2026-10-05T00:00:00Z'}]},persisted:true}
  assert.equal(validHandoff(valid),true)
  for (const field of ['release_id','product_id','request_id']) {
    const malformed = {...executed.evidence,[field]:{unexpected:'object'}}
    assert.equal(validHandoff({...valid,verified_evidence:{...valid.verified_evidence,actions:[{receipt:malformed,committed_at:'2026-10-05T00:00:00Z'}]}}),false)
  }
})

test('status and card-control lookups never resolve inherited prototype properties', () => {
  for (const status of ['__proto__','constructor','toString']) {
    assert.equal(translateStatus(messages.es,status),status)
    assert.deepEqual(availableActions(status),[])
  }
})

test('new conversation confirmation references reject non-text transaction fields before rendering', async () => {
  const active = {conversation_id:id,adapter:{provider:'engineering-stub',version:'1',mode:'stub'},events:[{event_id:'e',sequence:1,kind:'confirmation_prepared',trust:'backend',confirmation_id:id,data:{}}],next_after:null,last_sequence:1}
  for (const field of ['transaction_id','process_date']) {
    const malformed = {...pending,command:{product_id:'CARD-1',action:'unrecognized-charge',[field]:{unexpected:'object'}}}
    const h = harness(c => c.path === '/api/me/conversations' || c.path.includes('/conversations/') ? json(active) : c.path === `/api/me/action-confirmations/${id}` ? json(malformed) : undefined)
    await h.demo.login('customer','one','private-test-value')
    await h.demo.startConversation('es')
    await h.demo.refresh()
    assert.equal(h.demo.snapshot().error,'invalid_response')
    assert.deepEqual(h.demo.snapshot().confirmations,[])
  }
})

test('nullable source money is accepted without treating missing fields as zero', () => {
  const card = { product_id: 'CARD-1', product_type: 'Tarjeta Crédito', last_four: '4242', currency: 'USD', current_balance: null, simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture', last_updated: null }
  assert.ok(validCards({ release_id: 'r', cards: [card] }))
  assert.equal(validCards({ release_id: 'r', cards: [{ ...card, current_balance: undefined }] }), false)
  const movement = { transaction_id: 'T-1', transaction_date: '2026-01-01', process_date: '2026-01-02', amount: null, currency: 'USD', transaction_type: 'Purchase', transaction_status: 'Approved', merchant_name: null }
  assert.ok(validMovements({ release_id: 'r', movements: [movement], next_cursor: null }))
  assert.equal(validMovements({ release_id: 'r', movements: [{ ...movement, amount: {} }], next_cursor: null }), false)
  assert.equal(money(null, 'USD', 'es'), 'No disponible')
  assert.equal(money(null, 'USD', 'pt'), 'Indisponível')
  assert.notEqual(money('0', 'USD', 'es'), 'No disponible')
  assert.equal(sourceLabel('Withdrawal', 'pt'), 'Saque')
  assert.equal(sourceLabel('Approved', 'es'), 'Aprobada')
  assert.equal(sourceLabel('toString', 'es'), 'toString')
})

test('guided choices preserve conversation across language change and never confirm', async () => {
  const conversation = { conversation_id: id, adapter: { mode: 'injected', provider: 'fixture', version: '1' }, events: [], next_after: null }
  const h = harness(c => c.path.includes('/conversations') ? json(conversation) : undefined)
  await h.demo.login('customer', 'test', 'private-test-value')
  h.demo.setChatContext('not-owned')
  await h.demo.guidedRequest('block', 'es')
  assert.equal(h.calls.some(c => c.path.includes('/conversations')), false)
  h.demo.setChatContext('CARD-1')
  await h.demo.guidedRequest('pause', 'es')
  await h.demo.guidedRequest('block', 'pt')
  const turns = h.calls.filter(c => c.path.endsWith('/turns'))
  assert.equal(turns.length, 2)
  assert.equal(turns[0].path, turns[1].path)
  assert.equal(body(turns[1]).language, 'pt')
  assert.match(String(body(turns[1]).message), /Perda ou roubo.*CARD-1/)
  assert.equal(h.calls.some(c => c.path.endsWith('/confirm') || c.path.endsWith('/actions')), false)
  await h.demo.logout()
  assert.equal(h.demo.snapshot().chatContext, null)
})

test('stub limitations do not silently turn loss or charge review into a pause', async () => {
  const conversation = { conversation_id: id, adapter: { mode: 'stub', provider: 'stub', version: '1' }, events: [], next_after: null }
  const h = harness(c => c.path.includes('/conversations') ? json(conversation) : undefined)
  await h.demo.login('customer', 'test', 'private-test-value')
  h.demo.setChatContext('CARD-1')
  await h.demo.guidedRequest('block', 'es')
  assert.equal(h.demo.snapshot().error, 'unsupported_chat_action')
  assert.equal(h.calls.some(c => c.path.endsWith('/turns')), false)
  await h.demo.refresh()
  await h.demo.guidedRequest('pause', 'pt')
  assert.equal(body(h.calls.find(c => c.path.endsWith('/turns'))!).message, '/pause CARD-1')
})

test('selected movement reaches injected conversation with its composite identity', async () => {
  const movement = { transaction_id: 'T-2', transaction_date: '2026-01-01', process_date: '2026-01-02', amount: null, currency: 'USD', transaction_type: 'Purchase', transaction_status: 'Approved', merchant_name: null }
  const conversation = { conversation_id: id, adapter: { mode: 'injected', provider: 'fixture', version: '1' }, events: [], next_after: null }
  const h = harness(c => c.path.includes('/movements') ? json({ release_id: 'r', movements: [movement], next_cursor: null }) : c.path.includes('/conversations') ? json(conversation) : undefined)
  await h.demo.login('customer', 'test', 'private-test-value')
  h.demo.setChatContext('CARD-1', movement)
  assert.equal(h.demo.snapshot().chatContext, null)
  await h.demo.selectCard('CARD-1')
  h.demo.setChatContext('CARD-1', movement)
  await h.demo.guidedRequest('unrecognized-charge', 'pt')
  const turn = h.calls.find(c => c.path.endsWith('/turns'))!
  assert.match(String(body(turn).message), /T-2/)
  assert.match(String(body(turn).message), /2026-01-02/)
  assert.equal(h.calls.some(c => c.path.endsWith('/actions') || c.path.endsWith('/confirm')), false)
  h.demo.newChat()
  assert.equal(h.demo.snapshot().chatContext, null)
})

test('charge case needs a verified receipt and preserves exact payload on lost response', async () => {
  const command = { product_id: 'CARD-1', action: 'unrecognized-charge' as const, transaction_id: 'T-1', process_date: '2026-01-02' }
  const evidence = { ...executed.evidence!, action: 'unrecognized-charge' as const, simulator_state: 'ACTIVE', outcome: 'request_registered_for_human_review', request_id: 'c'.repeat(32) }
  const receipt = { ...executed, command, evidence }
  const handoff = { handoff_id: 'd'.repeat(32), status: 'queued', reason: 'card_support', severity: 'low', assigned_agent_id: null, queue: 'manual_review', release_id: 'r', triage: { language: 'es' }, model_context: { context: '' }, verified_evidence: { source: 'backend', release_id: 'r', actions: [{ receipt: evidence, committed_at: '2026-10-05T00:00:00Z' }] }, persisted: true }
  let attempts = 0
  const h = harness(c => {
    if (c.path.endsWith('/actions')) return json({ ...pending, command })
    if (c.path.endsWith('/confirm')) return json(receipt)
    if (c.path === '/api/me/handoffs' && c.options.method === 'POST') {
      if (++attempts === 1) throw new TypeError('lost response')
      handoff.model_context.context = String(body(c).context)
      return json(handoff)
    }
  })
  await h.demo.login('customer', 'test', 'private-test-value')
  await h.demo.prepare('CARD-1', 'unrecognized-charge', { transaction_id: 'T-1', process_date: '2026-01-02' })
  await h.demo.reportCharge(id, 'es')
  assert.equal(attempts, 0)
  await h.demo.confirmation(id, 'confirm')
  await h.demo.reportCharge(id, 'es')
  assert.equal(h.demo.snapshot().retryable, true)
  await h.demo.retry()
  const posts = h.calls.filter(c => c.path === '/api/me/handoffs' && c.options.method === 'POST')
  assert.deepEqual(body(posts[0]), body(posts[1]))
  assert.equal(headers(posts[0])['Idempotency-Key'], headers(posts[1])['Idempotency-Key'])
  assert.equal(body(posts[0]).product_id, 'CARD-1')
  assert.match(String(body(posts[0]).context), /T-1/)
  assert.match(String(body(posts[0]).context), /2026-01-02/)
  assert.match(String(body(posts[0]).context), new RegExp(evidence.request_id))
  assert.equal(h.demo.snapshot().reportCases[evidence.action_id], handoff.handoff_id)
  await h.demo.reportCharge(id, 'pt')
  assert.equal(attempts, 2)
  await h.demo.logout()
  assert.deepEqual(h.demo.snapshot().reportCases, {})
})

test('adapter labels identify only the declared local classifier and preserve stub/disabled precedence', () => {
  const classifier = { provider: 'intent-classifier', version: 'intent-router-v1', mode: 'injected' } as const
  assert.equal(adapterKind(classifier), 'classifier')
  assert.equal(messages.es[adapterKind(classifier)], 'Clasificador local de intenciones')
  assert.equal(messages.pt[adapterKind(classifier)], 'Classificador local de intenções')
  assert.equal(adapterKind({ ...classifier, provider: 'other-adapter' }), 'injected')
  assert.equal(adapterKind({ ...classifier, mode: 'stub' }), 'stub')
  assert.equal(adapterKind({ ...classifier, mode: 'disabled' }), 'disabled')
})

test('conversation descriptors require bounded provider/version metadata before UI labeling', () => {
  const adapter = { provider: 'intent-classifier', version: 'intent-router-v1', mode: 'injected' }
  const page = { conversation_id: id, adapter, events: [], next_after: null }
  assert.equal(validAdapter(adapter), true)
  assert.equal(validConversation(page), true)
  for (const malformed of [
    { mode: 'injected' },
    { ...adapter, provider: null },
    { ...adapter, provider: '' },
    { ...adapter, version: 'x'.repeat(101) },
    { ...adapter, mode: 'classifier' },
  ]) {
    assert.equal(validAdapter(malformed), false)
    assert.equal(validConversation({ ...page, adapter: malformed }), false)
  }
})

test('natural-language turn keeps selected card separate and preserves the exact context on replay', async () => {
  const active = { conversation_id: id, adapter: { provider: 'intent-classifier', version: 'v1', mode: 'injected' }, events: [], next_after: null, last_sequence: 0 }
  let attempts = 0
  const h = harness(c => {
    if (c.path.endsWith('/turns') && ++attempts === 1) throw new TypeError('lost response')
    if (c.path === '/api/me/conversations' || c.path.includes('/conversations/')) return json(active)
    return undefined
  })
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.startConversation('pt')
  await h.demo.turn('Quero pausar meu cartão', 'pt', 'CARD-1')
  assert.equal(h.demo.snapshot().retryable, true)
  await h.demo.turn('reactiva la otra', 'es', null)
  assert.equal(attempts, 1)
  await h.demo.retry()
  const turns = h.calls.filter(c => c.path.endsWith('/turns'))
  assert.equal(turns.length, 2)
  assert.deepEqual(body(turns[0]), { message: 'Quero pausar meu cartão', language: 'pt', selected_product_id: 'CARD-1' })
  assert.deepEqual(body(turns[1]), body(turns[0]))
  assert.equal(headers(turns[0])['Idempotency-Key'], headers(turns[1])['Idempotency-Key'])
  assert.equal(h.calls.some(c => c.path.endsWith('/confirm')), false)
})

test('turn context rejects an unknown card and is not inferred from account movement selection', async () => {
  const active = { conversation_id: id, adapter: { provider: 'intent-classifier', version: 'v1', mode: 'injected' }, events: [], next_after: null, last_sequence: 0 }
  const h = harness(c => c.path === '/api/me/conversations' || c.path.includes('/conversations/') ? json(active) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.startConversation('es')
  await h.demo.turn('pausa mi tarjeta', 'es', 'OTHER-CUSTOMER-CARD')
  assert.equal(h.demo.snapshot().error, 'http_422')
  assert.equal(h.calls.some(c => c.path.endsWith('/turns')), false)
  await h.demo.turn('pausa mi tarjeta', 'es')
  assert.equal(body(h.calls.find(c => c.path.endsWith('/turns'))!).selected_product_id, null)
})

test('ordered conversation card reads require backend trust and the existing typed resource shape', () => {
  const card = { product_id: 'CARD-2', product_type: 'Crédito', last_four: '1000', currency: 'USD', current_balance: '5.00', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }
  const event = { event_id: 'r', sequence: 1, kind: 'tool_result', trust: 'backend', data: { tool: 'get_cards', result: { release_id: 'r1', cards: [card, { ...card, product_id: 'CARD-1', last_four: '4242' }] } } } as ConversationEvent
  const read = conversationRead(event)
  assert.equal(read?.kind, 'cards')
  if (read?.kind === 'cards') assert.deepEqual(read.value.cards.map(c => c.product_id), ['CARD-2', 'CARD-1'])
  assert.equal(conversationRead({ ...event, trust: 'untrusted' }), null)
  assert.equal(conversationRead({ ...event, kind: 'answer' }), null)
  assert.equal(conversationRead({ ...event, data: { tool: 'get_cards', result: { release_id: 'r1', cards: [{ ...card, current_balance: {} }] } } }), null)
  const single = conversationRead({ ...event, data: { tool: 'get_card', result: { release_id: 'r1', card } } })
  assert.equal(single?.kind, 'cards')
  if (single?.kind === 'cards') assert.deepEqual(single.value.cards, [card])
})

test('movement read results remain typed historical data and cannot become action evidence', () => {
  const event = { event_id: 'r', sequence: 1, kind: 'tool_result', trust: 'backend', data: { tool: 'get_movements', result: { release_id: 'r1', next_cursor: null, movements: [{ transaction_id: 'T1', transaction_date: '2026-01-01', process_date: '2026-01-01', amount: '1.00', currency: 'USD', transaction_type: 'purchase', transaction_status: 'posted', merchant_name: null }] } } } as ConversationEvent
  assert.equal(conversationRead(event)?.kind, 'movements')
  assert.equal(conversationRead({ ...event, trust: 'untrusted' }), null)
  assert.equal(conversationRead({ ...event, data: { ...event.data, tool: 'pause_card' } }), null)
  assert.equal(conversationRead({ ...event, data: { tool: 'get_movements', result: { release_id: 'r1', next_cursor: 1, movements: [] } } }), null)
})


test('card limit and product update metadata remain typed, nullable and historically labeled', () => {
  const card = { product_id: 'CARD-1', product_type: 'Crédito', last_four: '4242', currency: 'USD', current_balance: '125.50', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }
  const resource = (fields: object) => ({ release_id: 'r1', cards: [{ ...card, ...fields }] })
  assert.equal(validCards(resource({ credit_limit: '1000.00', last_updated: '2023-06-17T10:00:00' })), true)
  assert.equal(validCards(resource({ credit_limit: null, last_updated: null })), true)
  assert.equal(validCards(resource({ credit_limit: '0.00' })), true)
  assert.equal(validCards(resource({})), true)
  for (const credit_limit of [{}, [], 1000, '', 'NaN', 'Infinity', '1000 USD', '<b>1000</b>']) assert.equal(validCards(resource({ credit_limit })), false)
  for (const last_updated of [{}, 1, 'yesterday', '2023-06-17T25:00:00']) assert.equal(validCards(resource({ last_updated })), false)
  const event = { event_id: 'r', sequence: 1, kind: 'tool_result', trust: 'backend', data: { tool: 'get_card', result: { release_id: 'r1', card: { ...card, credit_limit: '1000.00' } } } } as ConversationEvent
  const read = conversationRead(event)
  assert.equal(read?.kind, 'cards')
  if (read?.kind === 'cards') assert.equal(read.value.cards[0].credit_limit, '1000.00')
  assert.equal(messages.es.creditLimit, 'Límite de crédito')
  assert.equal(messages.pt.creditLimit, 'Limite de crédito')
})

test('confirmation card labels match exact owned identifiers and preserve unknown ID fallback', () => {
  const cards = [{ product_id: 'CARD-1', product_type: 'Crédito', last_four: '4242', currency: 'USD', current_balance: '1.00', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }]
  assert.equal(cardLabel('CARD-1', cards), 'Crédito · 4242')
  assert.equal(cardLabel('OTHER-CARD-1', cards), 'OTHER-CARD-1')
})

test('only acknowledged turns may clear the matching composer draft', async () => {
  const active = { conversation_id: id, adapter: { provider: 'intent-classifier', version: 'v1', mode: 'injected' }, events: [], next_after: null, last_sequence: 0 }
  for (const status of [422, 409, 200]) {
    const h = harness(c => c.path === '/api/me/conversations' ? json(active) : c.path.endsWith('/turns') ? json(status === 200 ? active : {}, status) : c.path.includes('/conversations/') ? json(active) : undefined)
    await h.demo.login('customer', 'one', 'private-test-value')
    await h.demo.startConversation('es')
    assert.equal(await h.demo.turn('consulta mi límite', 'es', 'CARD-1'), status === 200)
    assert.equal(h.demo.snapshot().retryable, false)
  }
  const h = harness(c => c.path === '/api/me/conversations' ? json(active) : c.path.endsWith('/turns') ? Promise.reject(new TypeError('lost response')) : c.path.includes('/conversations/') ? json(active) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.startConversation('es')
  assert.equal(await h.demo.turn('consulta mi límite', 'es', 'CARD-1'), false)
  assert.equal(h.demo.snapshot().retryable, true)
  assert.equal(await h.demo.turn('another draft', 'es', 'CARD-1'), false)
})

test('uncertain replay rejected with 4xx never acknowledges or discards the original message', async () => {
  const active = { conversation_id: id, adapter: { provider: 'intent-classifier', version: 'v1', mode: 'injected' }, events: [], next_after: null, last_sequence: 0 }
  for (const status of [422, 409]) {
    let attempt = 0
    const h = harness(c => c.path === '/api/me/conversations' ? json(active) : c.path.endsWith('/turns') ? json({}, ++attempt === 1 ? 503 : status) : c.path.includes('/conversations/') ? json(active) : undefined)
    await h.demo.login('customer', 'one', 'private-test-value')
    await h.demo.startConversation('pt')
    assert.equal(await h.demo.turn('Qual é meu limite?', 'pt', 'CARD-1'), false)
    assert.equal(h.demo.snapshot().acknowledgedTurn, null)
    assert.equal(h.demo.snapshot().retryable, true)
    await h.demo.retry()
    assert.equal(h.demo.snapshot().acknowledgedTurn, null)
    assert.equal(h.demo.snapshot().retryable, false)
    assert.equal(h.demo.snapshot().error, `http_${status}`)
    const calls = h.calls.filter(c => c.path.endsWith('/turns'))
    assert.deepEqual(body(calls[0]), body(calls[1]))
    assert.equal(headers(calls[0])['Idempotency-Key'], headers(calls[1])['Idempotency-Key'])
  }
})

test('accepted exact replay acknowledges its original text and key, and logout clears that ownership', async () => {
  const active = { conversation_id: id, adapter: { provider: 'intent-classifier', version: 'v1', mode: 'injected' }, events: [], next_after: null, last_sequence: 0 }
  let attempt = 0
  const h = harness(c => c.path === '/api/me/conversations' ? json(active) : c.path.endsWith('/turns') ? json(++attempt === 1 ? {} : active, attempt === 1 ? 503 : 200) : c.path.includes('/conversations/') ? json(active) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  await h.demo.startConversation('es')
  await h.demo.turn('consulta mi límite', 'es', 'CARD-1')
  assert.equal(h.demo.snapshot().acknowledgedTurn, null)
  await h.demo.retry()
  const calls = h.calls.filter(c => c.path.endsWith('/turns'))
  assert.deepEqual(h.demo.snapshot().acknowledgedTurn, { key: headers(calls[0])['Idempotency-Key'], message: 'consulta mi límite' })
  assert.deepEqual(body(calls[0]), body(calls[1]))
  assert.equal(headers(calls[0])['Idempotency-Key'], headers(calls[1])['Idempotency-Key'])
  await h.demo.logout()
  assert.equal(h.demo.snapshot().acknowledgedTurn, null)
})

test('charge-case association rejects empty, unrelated or altered backend evidence and context', async () => {
  const command = { product_id: 'CARD-1', action: 'unrecognized-charge' as const, transaction_id: 'T-1', process_date: '2026-01-02' }
  const evidence = { ...executed.evidence!, action: 'unrecognized-charge' as const, simulator_state: 'ACTIVE', outcome: 'request_registered_for_human_review', request_id: 'c'.repeat(32) }
  for (const mismatch of ['empty', 'product_id', 'request_id', 'action_id', 'context', 'handoff_id', 'blank_handoff_id']) {
    const h = harness(c => {
      if (c.path.endsWith('/actions')) return json({ ...pending, command })
      if (c.path.endsWith('/confirm')) return json({ ...executed, command, evidence })
      if (c.path === '/api/me/handoffs' && c.options.method === 'POST') {
        const saved = { ...evidence, ...(mismatch === 'product_id' ? { product_id: 'CARD-OTHER' } : {}), ...(mismatch === 'request_id' ? { request_id: 'e'.repeat(32) } : {}), ...(mismatch === 'action_id' ? { action_id: 'f'.repeat(32) } : {}) }
        return json({ handoff_id: mismatch === 'handoff_id' ? '' : mismatch === 'blank_handoff_id' ? ' \t' : 'd'.repeat(32), status: 'queued', reason: 'card_support', severity: 'low', assigned_agent_id: null, queue: 'manual_review', release_id: 'r', triage: { language: 'es' }, model_context: { context: mismatch === 'context' ? 'unrelated charge' : body(c).context }, verified_evidence: { source: 'backend', release_id: 'r', actions: mismatch === 'empty' ? [] : [{ receipt: saved, committed_at: '2026-10-05T00:00:00Z' }] }, persisted: true })
      }
    })
    await h.demo.login('customer', 'test', 'private-test-value')
    await h.demo.prepare('CARD-1', 'unrecognized-charge', { transaction_id: 'T-1', process_date: '2026-01-02' })
    await h.demo.confirmation(id, 'confirm')
    await h.demo.reportCharge(id, 'es')
    assert.equal(h.demo.snapshot().error, 'invalid_response', mismatch)
    assert.deepEqual(h.demo.snapshot().reportCases, {}, mismatch)
  }
})

test('product timestamp calendar dates cannot normalize impossible historical evidence', () => {
  const card = { product_id: 'CARD-1', product_type: 'credit', last_four: '4242', currency: 'USD', current_balance: '1', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }
  for (const last_updated of ['2023-02-30T10:00:00Z', '2023-02-29T10:00:00', '2026-04-31T10:00:00-03:00', '0000-01-01T00:00:00Z']) assert.equal(validCards({ release_id: 'r', cards: [{ ...card, last_updated }] }), false)
  for (const last_updated of ['2024-02-29T10:00:00Z', '2026-01-01T00:00:00+03:00']) assert.equal(validCards({ release_id: 'r', cards: [{ ...card, last_updated }] }), true)
})

test('source date formatting rejects impossible days and preserves valid leap dates in both locales', () => {
  for (const locale of ['es', 'pt'] as const) {
    for (const value of ['2026-02-30', '2025-02-29', '2026-04-31', '0000-01-01']) assert.equal(sourceDate(value, locale), sourceDate(null, locale))
    assert.notEqual(sourceDate('2024-02-29', locale), sourceDate(null, locale))
  }
})

test('confirmation product labels use the requested glossary without changing ownership lookup', () => {
  const cards = [{ product_id: 'CARD-1', product_type: 'Tarjeta Crédito', last_four: '4242', currency: 'USD', current_balance: '1', simulator_state: 'ACTIVE', source_kind: 'team_synthetic', balance_semantics: 'team_fixture' }]
  assert.equal(cardLabel('CARD-1', cards, value => sourceLabel(value, 'pt')), 'Cartão de crédito · 4242')
  assert.equal(cardLabel('OTHER', cards, value => sourceLabel(value, 'pt')), 'OTHER')
})

test('legacy or blank charge targets cannot create or associate a case', async () => {
  const evidence = { ...executed.evidence!, action: 'unrecognized-charge' as const, simulator_state: 'ACTIVE', outcome: 'request_registered_for_human_review', request_id: 'c'.repeat(32) }
  for (const target of [undefined, { transaction_id: '', process_date: '2026-01-02' }, { transaction_id: ' \t', process_date: '2026-01-02' }, { transaction_id: 'T-1', process_date: '' }, { transaction_id: 'T-1', process_date: ' \n' }, ...['2026-02-30', '2025-02-29', '2026-04-31', '0000-01-01', 'invalid', '2026-01-02T00:00:00Z', ' 2026-01-02'].map(process_date => ({ transaction_id: 'T-1', process_date }))]) {
    const command = { product_id: 'CARD-1', action: 'unrecognized-charge' as const, ...target }
    const h = harness(c => c.path.endsWith('/actions') ? json({ ...pending, command }) : c.path.endsWith('/confirm') ? json({ ...executed, command, evidence }) : undefined)
    await h.demo.login('customer', 'test', 'private-test-value')
    await h.demo.prepare('CARD-1', 'unrecognized-charge', target)
    await h.demo.confirmation(id, 'confirm')
    assert.equal(h.demo.snapshot().confirmations[0].status, 'executed')
    await h.demo.reportCharge(id, 'es')
    assert.equal(h.calls.some(c => c.path === '/api/me/handoffs' && c.options.method === 'POST'), false)
    assert.deepEqual(h.demo.snapshot().reportCases, {})
  }
})


test('chat context can be cleared before sending an unrelated turn', async () => {
  const active = { conversation_id: id, adapter: { provider: 'fixture', version: '1', mode: 'injected' }, events: [], next_after: null }
  const h = harness(c => c.path.includes('/conversations') ? json(active) : undefined)
  await h.demo.login('customer', 'one', 'private-test-value')
  h.demo.setChatContext('CARD-1')
  await h.demo.startConversation('es')
  await h.demo.turn('card question', 'es', h.demo.snapshot().chatContext?.product_id ?? null)
  h.demo.setChatContext('')
  assert.equal(h.demo.snapshot().chatContext, null)
  await h.demo.turn('unrelated question', 'es', h.demo.snapshot().chatContext?.product_id ?? null)
  const calls = h.calls.filter(c => c.path.endsWith('/turns'))
  assert.equal(body(calls[0]).selected_product_id, 'CARD-1')
  assert.equal(body(calls[1]).selected_product_id, null)
})

test('charge identity requires an exact valid calendar date', () => {
  for (const process_date of ['2026-02-30', '2025-02-29', '2026-04-31', '0000-01-01', 'invalid', '2026-1-2', '2026-01-02T00:00:00Z', ' 2026-01-02', undefined]) assert.equal(validChargeIdentity({ action: 'unrecognized-charge', product_id: 'CARD-1', transaction_id: 'T-1', process_date }), false)
  assert.equal(validChargeIdentity({ action: 'unrecognized-charge', product_id: 'CARD-1', transaction_id: 'T-1', process_date: '2024-02-29' }), true)
})
