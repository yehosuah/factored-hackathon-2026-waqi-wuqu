import type { Role } from './api'
import type { Locale, Messages } from './i18n'

export function Header({ text, locale, setLocale, signedIn, role, route, logout }: {
  text: Messages
  locale: Locale
  setLocale: (locale: Locale) => void
  signedIn: boolean
  role: Role
  route: string
  logout: () => void
}) {
  const links = role === 'customer'
    ? [{ href: '#home', label: text.home }, { href: '#cards', label: text.cards }, { href: '#chat', label: text.chat }]
    : [{ href: '#handoffs-title', label: text.handoffs }]
  return <header className="app-header">
    <a className="brand" href="#home">Waqi'wuqu</a>
    {signedIn && <nav className="header-navigation" aria-label={text.overview}>
      {links.map(link => <a key={link.href} href={link.href} className={(route || '#home') === link.href ? 'current' : ''} aria-current={(route || '#home') === link.href ? 'page' : undefined}>{link.label}</a>)}
    </nav>}
    <div className="header-controls">
      <span className="environment">{text.label}</span>
      <label className="language">
        <span className="sr-only">{text.language}</span>
        <select aria-label={text.language} value={locale} onChange={e => setLocale(e.target.value as Locale)}>
          <option value="es">Español</option><option value="pt">Português</option>
        </select>
      </label>
      {signedIn && <button className="header-logout" onClick={logout}>{text.logout}</button>}
    </div>
  </header>
}
