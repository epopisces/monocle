import { NavLink } from 'react-router-dom'
import './LeftNav.css'

interface LeftNavProps {
  collapsed: boolean
}

const NAV_ITEMS = [
  { to: '/',       icon: '💬', label: 'Chat' },
  { to: '/docs',   icon: '📄', label: 'Docs' },
  { to: '/search', icon: '🔍', label: 'Search' },
  { to: '/graph',  icon: '◉',  label: 'Graph' },
  { to: '/stats',  icon: '📊', label: 'Stats' },
]

export default function LeftNav({ collapsed }: LeftNavProps) {
  return (
    <nav
      className={`left-nav ${collapsed ? 'left-nav--collapsed' : ''}`}
      aria-label="Main navigation"
      data-testid="left-nav"
    >
      {NAV_ITEMS.map(({ to, icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `left-nav__item ${isActive ? 'left-nav__item--active' : ''}`
          }
          title={collapsed ? label : undefined}
        >
          <span className="left-nav__icon" aria-hidden="true">{icon}</span>
          {!collapsed && <span className="left-nav__label">{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}
