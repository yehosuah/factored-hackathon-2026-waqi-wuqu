import type { State } from './demo'
import type { Locale, Messages } from './i18n'

const copy = {
  es: { greeting: 'Hola', intro: 'Tu espacio, en un solo lugar.', body: 'Consulta el estado de tus tarjetas y da seguimiento a tus solicitudes.', cards: 'Consulta tus productos y movimientos históricos.', requests: 'Acciones que esperan tu confirmación.', cases: 'Solicitudes de atención que siguen abiertas.', open: 'Ver mis tarjetas', subtitle: 'Una mirada a tu cuenta', },
  pt: { greeting: 'Olá', intro: 'Seu espaço, em um só lugar.', body: 'Consulte o estado dos seus cartões e acompanhe suas solicitações.', cards: 'Consulte seus produtos e movimentos históricos.', requests: 'Ações que aguardam sua confirmação.', cases: 'Solicitações de atendimento que continuam abertas.', open: 'Ver meus cartões', subtitle: 'Uma visão da sua conta', },
}

export function HomePage({ state, text, locale, refresh, locked }: {
  state: State; text: Messages; locale: Locale; refresh: () => void; locked: boolean
}) {
  const words = copy[locale]
  const stats = [
    { label: text.cardCount, count: state.cards.length, detail: words.cards, href: '#cards' },
    { label: text.requests, count: state.confirmations.filter(c => c.status === 'pending').length, detail: words.requests, href: '#cards' },
    { label: text.cases, count: state.handoffs.filter(h => !['resolved', 'cancelled'].includes(h.status)).length, detail: words.cases, href: '#home-cases' },
  ]
  return <section className="home-page" aria-labelledby="home-title">
    <div className="hero home-hero">
      <div><p className="eyebrow">{text.home}</p><h1 id="home-title">{words.greeting}, {state.username}.</h1><p className="home-intro">{words.intro}</p><p className="muted">{words.body}</p></div>
      <button className="secondary" disabled={locked} onClick={refresh}>{text.refresh}</button>
    </div>
    <div className="home-section-heading"><h2>{words.subtitle}</h2><a href="#cards">{words.open} <span aria-hidden="true">↗</span></a></div>
    <div className="home-stats">{stats.map(stat => <a className="home-stat" key={stat.label} href={stat.href}><span>{stat.label}</span><strong>{stat.count.toString().padStart(2, '0')}</strong><p>{stat.detail}</p><span className="home-stat-arrow" aria-hidden="true">↗</span></a>)}</div>
  </section>
}
