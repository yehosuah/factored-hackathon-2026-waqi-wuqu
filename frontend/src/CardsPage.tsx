import type { Demo, State } from './demo'
import { availableActions } from './contracts'
import { translateStatus, type Locale, type Messages } from './i18n'

import { money, sourceDate, sourceLabel, workflowCopy } from './workflow-copy'

export function CardsPage({ state, demo, text, locked, productName, locale }: {
  state: State; demo: Demo; text: Messages; locked: boolean; productName: string; locale: Locale
}) {
  const copy = workflowCopy[locale]
  const visibleCard = state.cards.find(c => c.product_id === state.selected) ?? state.cards[0]
  return (
<div className="workspace">
                  <div className="account">
                    <section className="panel" aria-labelledby="cards-title">
                      <div className="section-heading">
                        <h2 id="cards-title">{text.cards}</h2>
                      </div>
                      {state.cards.length > 1 && (
                        <label className="card-selector">
                          {text.product}
                          <select
                            disabled={locked}
                            value={visibleCard?.product_id ?? ''}
                            onChange={(e) =>
                              void demo.selectCard(e.target.value)
                            }
                          >
                            {state.cards.map((c) => (
                              <option value={c.product_id} key={c.product_id}>
                                {sourceLabel(c.product_type, locale)} · {c.last_four} ·{' '}
                                {translateStatus(text, c.simulator_state)}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      <div className="cards">
                        {state.cards.length === 0 && (
                          <p className="empty-state">{text.noCards}</p>
                        )}
                        {(visibleCard ? [visibleCard] : []).map((card) => (
                          <article
                            className="card-container"
                            key={card.product_id}
                          >
                            <div className="card">
                              <div className="section-heading">
                                <span className="card-brand">
                                  {productName}
                                </span>
                                <span>{sourceLabel(card.product_type, locale)}</span>
                              </div>
                              <p className="card-number">
                                •••• •••• •••• {card.last_four}
                              </p>
                              <div className="section-heading">
                                <span>{card.currency}</span>
                                <span className="card-state">
                                  {translateStatus(text, card.simulator_state)}
                                </span>
                              </div>
                            </div>
                            <div className="card-details">
                              <div className="section-heading">
                                <div>
                                  <small>{text.balance}</small>
                                  <p className="balance">
                                    {money(card.current_balance, card.currency, locale)}
                                  </p>
                                </div>
                                <button
                                  className="secondary"
                                  disabled={locked}
                                  onClick={() =>
                                    void demo.selectCard(card.product_id)
                                  }
                                >
                                  {text.details}
                                </button>
                              </div>
                              <div className="source-context"><p>{text.source}: {sourceLabel(card.source_kind, locale)}</p><p>{copy.updated}: {sourceDate(card.last_updated, locale)}</p><details><summary>{text.historical}</summary><p>{copy.cutoffNote}</p><p>{text.release}: <span className="mono">{state.release}</span></p></details></div>
                              <p>{text.creditLimit}: {card.credit_limit == null ? text.limitUnavailable : money(card.credit_limit, card.currency, locale)}</p>
                              {card.simulator_state === 'BLOCKED' && <p className="workflow-note">{copy.blockHelp}</p>}
                              <div className="card-control">
                                {availableActions(card.simulator_state).map((action, index) => (
                                  <button key={action} className={index === 0 ? '' : 'secondary'} disabled={locked} onClick={() => void demo.prepare(card.product_id, action)}>{text[action]}</button>
                                ))}
                              </div>
                            </div>
                          </article>
                        ))}
                      </div>
                    </section>
                    {state.movements && (
                      <section className="panel">
                        <h2>{text.movements}</h2><p className="source-context">{text.historical}</p>
                        <div className="table-wrap">
                          <table>
                            <caption className="sr-only">
                              {text.movements} · {state.selected}
                            </caption>
                            <thead>
                              <tr>
                                <th>{text.date}</th>
                                <th>{text.description}</th>
                                <th className="amount">{text.amount}</th>
                                <th>{text.status}</th>
                                <th>
                                  <span className="sr-only">
                                    {text.command}
                                  </span>
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {state.movements.movements.map((m) => (
                                <tr
                                  key={`${m.transaction_id}:${m.process_date}`}
                                >
                                  <td>{sourceDate(m.transaction_date, locale)}<small>{copy.processDate}: {sourceDate(m.process_date, locale)}</small></td>
                                  <td>
                                    <strong>
                                      {m.merchant_name ?? sourceLabel(m.transaction_type, locale)}
                                    </strong>
                                    <small>{sourceLabel(m.transaction_type, locale)}</small>
                                  </td>
                                  <td className="amount">
                                    {money(m.amount, m.currency, locale)}
                                  </td>
                                  <td>
                                    <span className="transaction-status">
                                      {sourceLabel(m.transaction_status, locale)}
                                    </span>
                                  </td>
                                  <td>
                                    <details>
                                      <summary>{text.management}</summary>
                                      <button
                                        className="text-button"
                                        disabled={locked}
                                        onClick={() =>
                                          void demo.prepare(
                                            state.selected,
                                            'unrecognized-charge',
                                            {
                                              transaction_id: m.transaction_id,
                                              process_date: m.process_date,
                                            },
                                          )
                                        }
                                      >
                                        {text['unrecognized-charge']}
                                      </button>
                                      <button className="text-button" disabled={locked} onClick={() => { demo.setChatContext(state.selected, m); window.location.hash = 'chat' }}>{copy.chatMovement}</button>
                                    </details>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {state.movements.movements.length === 0 && (
                          <p className="empty-state">{text.empty}</p>
                        )}
                        {state.movements.next_cursor && (
                          <button
                            className="secondary"
                            disabled={locked}
                            onClick={() =>
                              void demo.selectCard(
                                state.selected,
                                state.movements?.next_cursor ?? undefined,
                              )
                            }
                          >
                            {text.more}
                          </button>
                        )}
                      </section>
                    )}
                  </div>

                </div>
  )
}
