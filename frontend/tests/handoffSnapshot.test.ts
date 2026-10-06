import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validHandoffSnapshot, snapshotFact, snapshotDiagnostics, type SnapshotEvent } from '../src/handoffSnapshot.ts'
import { validHandoff } from '../src/contracts.ts'
const id = 'a'.repeat(32)
const base = { sequence: 1, turn_id: id, recorded_at: '2026-10-05T01:00:00Z' }
const message = { ...base, kind: 'user_message', trust: 'customer_provided', verified: false, text: '<script>customer text</script>', text_truncated: false }
const read = { ...base, sequence: 2, kind: 'tool_result', trust: 'backend', verified: true, status: 'read_verified', tool: 'get_card', facts: { cards: [{ product_id: 'CARD-1', credit_limit: null }], rows_truncated: false } }
const snapshot = { contract_version: 'handoff-conversation-v1', source: 'persisted_conversation_events', conversation_id: id, last_sequence: 2, events_truncated: false, events: [message, read] }
function history(events: unknown[]) {
  const first = events[0] as { sequence: number } | undefined
  const last = events.at(-1) as { sequence: number } | undefined
  return { ...snapshot, events, last_sequence: last?.sequence ?? 0, events_truncated: (first?.sequence ?? 1) > 1 }
}
test('saved failures expose independent optional diagnostics without inventing success or blank traces', () => {
  const error = {...base, kind:'error', trust:'backend', verified:false, status:'failed_or_unknown'}
  for (const [diagnostics, expected] of [
    [{tool:'get_card'}, ['get_card']],
    [{tool_error:'card_not_owned'}, ['card_not_owned']],
    [{code:'tool_failed',tool:'get_card',tool_error:'card_not_owned'}, ['tool_failed','get_card','card_not_owned']],
    [{code:'',tool:'  ',tool_error:''}, []],
    [{}, []],
    [{tool_error:'<img src=x onerror=alert(1)>'}, ['<img src=x onerror=alert(1)>']],
  ] as const) {
    const event = {...error,...diagnostics}
    assert.equal(validHandoffSnapshot(history([event])),true)
    assert.deepEqual(snapshotDiagnostics(event as SnapshotEvent),expected)
  }
  assert.deepEqual(snapshotDiagnostics(read as SnapshotEvent),[])
})
test('handoff snapshots accept bounded provided text and backend read facts in persisted order', () => {
  assert.equal(validHandoffSnapshot(snapshot), true)
  assert.equal(validHandoffSnapshot(history( [{ ...message, text: '😀'.repeat(200) }] )), true)
  for (const events of [[read,message], [message,message], [{...message,text:'x'.repeat(201)}], [{...message,text:{}}], [{...read,verified:false}], [{...read,facts:{cards:[{product_id:{}}],rows_truncated:false}}], [{...read,facts:{cards:Array(11).fill({}),rows_truncated:true}}], Array(21).fill(message)]) assert.equal(validHandoffSnapshot(history(events)),false)
})
test('snapshot text cannot assert verified evidence and receipts must match executed command', () => {
  const receipt = { action_id:id,product_id:'CARD-1',action:'pause',status:'succeeded',outcome:'state_change_verified',simulator_state:'PAUSED',simulated:true,source_kind:'team_synthetic',release_id:'synthetic-1' }
  const action = {...base,kind:'confirmation_status',trust:'backend',verified:true,status:'executed',confirmation_id:id,command:{action:'pause',product_id:'CARD-1'},receipt}
  assert.equal(validHandoffSnapshot(history([action])),true)
  for (const event of [{...message,verified:true},{...action,status:'pending'},{...action,command:{action:'block',product_id:'CARD-1'}},{...action,receipt:{...receipt,simulated:false}},{...action,verified:false}]) assert.equal(validHandoffSnapshot(history([event])),false)
  for (const status of ['pending','cancelled','expired','stale','executed']) assert.equal(validHandoffSnapshot(history([{...action,status,verified:false,receipt:undefined}])),true)
})
test('failed and unknown attempts stay unverified and historical cases can omit the snapshot', () => {
  const events = [{...base,kind:'error',trust:'backend',verified:false,status:'failed_or_unknown',code:'not_owned'}, {...base,sequence:2,kind:'future_event',trust:'untrusted',verified:false,status:'unknown'}]
  assert.equal(validHandoffSnapshot(history(events)),true)
  assert.equal(validHandoffSnapshot(history([{...events[0],code:{}}])),false)
  for (const event of [{...message,facts:{}},{...events[1],command:{}},{...read,facts:{...read.facts,movements:{}}}]) assert.equal(validHandoffSnapshot(history([event])),false)
  const handoff = {handoff_id:id,status:'assigned',reason:'card_support',severity:'low',assigned_agent_id:'AGENT-1',queue:null,release_id:'synthetic-1',triage:{language:'es'},model_context:{summary:'Synthetic case'},verified_evidence:{source:'backend',release_id:'synthetic-1',actions:[]},persisted:true}
  for (const conversation_snapshot of [undefined,null,snapshot]) assert.equal(validHandoff({...handoff,conversation_snapshot}),true)
  assert.equal(validHandoff({...handoff,conversation_snapshot:{...snapshot,last_sequence:0}}),false)
})

test('valid sparse snapshot facts display unavailable values without inventing currency or amounts', () => {
  const sparse = {...read,facts:{cards:[{}],rows_truncated:false}}
  assert.equal(validHandoffSnapshot(history([sparse])),true)
  for (const missing of [undefined,null,'','  ']) assert.equal(snapshotFact(missing),'—')
  assert.equal(snapshotFact('0.00'),'0.00')
  assert.equal(snapshotFact('USD'),'USD')
  const movement = {...read,tool:'get_movements',facts:{movements:[{}],rows_truncated:false}}
  assert.equal(validHandoffSnapshot(history([movement])),true)
})

test('authorized empty snapshot reads remain valid distinct results for explicit empty-state rendering', () => {
  for (const [tool, rows] of [['get_cards', 'cards'], ['get_movements', 'movements']]) {
    assert.equal(validHandoffSnapshot(history([{...read,tool,facts:{[rows]:[],rows_truncated:false}}])),true)
    assert.equal(validHandoffSnapshot(history([{...read,tool,facts:{rows_truncated:false}}])),false)
  }
})

test('optional saved charge targets remain requested context with historical fallback and unchanged receipt authority', () => {
  const command = {action:'unrecognized-charge',product_id:'CARD-1',transaction_id:'tx1',process_date:'2026-01-02'}
  const event = {...base,kind:'confirmation_status',trust:'backend',verified:false,status:'pending',confirmation_id:id,command}
  for (const status of ['pending','cancelled','expired','stale']) {
    for (const target of [command,{action:command.action,product_id:command.product_id}]) {
      assert.equal(validHandoffSnapshot(history([{...event,status,command:target}])),true)
      assert.equal(validHandoffSnapshot(history([{...event,status,command:target,verified:true}])),false)
    }
  }
  const receipt = {action_id:id,request_id:id,product_id:'CARD-1',action:'unrecognized-charge',status:'succeeded',outcome:'request_registered_for_human_review',simulator_state:'ACTIVE',simulated:true,source_kind:'team_synthetic',release_id:'synthetic-1'}
  const executed = {...event,status:'executed',verified:true,receipt}
  assert.equal(validHandoffSnapshot(history([executed])),true)
  for (const invalid of [{...executed,receipt:undefined},{...executed,status:'cancelled'},{...executed,receipt:{...receipt,product_id:'OTHER'}},{...executed,receipt:{...receipt,outcome:'refund_completed'}}]) assert.equal(validHandoffSnapshot(history([invalid])),false)
})

test('saved charge targets enforce backend bounds, real dates and action-specific projection', () => {
  const command = {action:'unrecognized-charge',product_id:'CARD-1',transaction_id:'tx1',process_date:'2026-01-02'}
  const event = {...base,kind:'confirmation_prepared',trust:'backend',verified:false,status:'pending',confirmation_id:id,command}
  for (const change of [{transaction_id:''},{transaction_id:' '},{transaction_id:'x'.repeat(31)},{transaction_id:null},{transaction_id:{}},{process_date:'2026-02-30'},{process_date:'2025-02-29'},{process_date:'0000-01-01'},{process_date:'2026-1-2'},{process_date:null},{process_date:{}},{merchant:'unprojected'},{action:'pause'}]) assert.equal(validHandoffSnapshot(history([{...event,command:{...command,...change}}])),false)
  for (const change of [{transaction_id:'😀'.repeat(30)},{process_date:'2024-02-29'},{transaction_id:undefined},{process_date:undefined}]) assert.equal(validHandoffSnapshot(history([{...event,command:{...command,...change}}])),true)
})

test('complete saved histories start at one with no gaps and all histories reach their advertised last event', () => {
  for (const invalid of [
    { ...snapshot, events: [read] },
    { ...snapshot, events: [message] },
    { ...snapshot, events: [], last_sequence: 2 },
    { ...snapshot, events: [{ ...read, sequence: 10 }], last_sequence: 20, events_truncated: true },
    { ...snapshot, events: [message, { ...read, sequence: 3 }], last_sequence: 3 },
  ]) assert.equal(validHandoffSnapshot(invalid), false)
  assert.equal(validHandoffSnapshot({ ...snapshot, events: [read], events_truncated: true }), true)
  assert.equal(validHandoffSnapshot({ ...snapshot, events: [], last_sequence: 0 }), true)
})

test('saved unverified action commands require an identifiable nonblank card', () => {
  for (const status of ['pending', 'cancelled', 'expired', 'stale'])
    for (const product_id of ['', ' ', '\t\n'])
      assert.equal(validHandoffSnapshot(history([{ ...base, kind: 'confirmation_status', trust: 'backend', verified: false, status, confirmation_id: id, command: { action: 'pause', product_id } }])), false)
})
