import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import { CHAT_DOCUMENT_DRAG_TYPE, decodeChatDocumentDragPayload, type ChatDocumentDragPayload } from '../Chat/chatGroundingDnd'
import './LeftNav.css'

interface LeftNavProps {
  collapsed: boolean
  onChatDocumentDrop?: (payload: ChatDocumentDragPayload) => void
}

const NAV_ITEMS = [
  { to: '/',       icon: '💬', label: 'Chat' },
  { to: '/docs',   icon: '📄', label: 'Docs' },
  { to: '/search', icon: '🔍', label: 'Search' },
  { to: '/graph',  icon: '◉',  label: 'Graph' },
  { to: '/stats',  icon: '📊', label: 'Stats' },
]

export default function LeftNav({ collapsed, onChatDocumentDrop }: LeftNavProps) {
  const [chatDropActive, setChatDropActive] = useState(false)

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
            `left-nav__item ${isActive ? 'left-nav__item--active' : ''}${to === '/' && chatDropActive ? ' left-nav__item--drop-active' : ''}`
          }
          title={collapsed ? label : undefined}
          data-testid={to === '/' ? 'left-nav-chat-link' : undefined}
          onDragOver={event => {
            if (to !== '/' || !onChatDocumentDrop) return
            const dragTypes = Array.from(event.dataTransfer.types ?? [])
            if (!dragTypes.includes(CHAT_DOCUMENT_DRAG_TYPE)) return
            event.preventDefault()
            event.dataTransfer.dropEffect = 'copy'
            setChatDropActive(true)
          }}
          onDragLeave={() => {
            if (to === '/') setChatDropActive(false)
          }}
          onDrop={event => {
            if (to !== '/' || !onChatDocumentDrop) return
            event.preventDefault()
            setChatDropActive(false)
            const payload = decodeChatDocumentDragPayload(event.dataTransfer.getData(CHAT_DOCUMENT_DRAG_TYPE))
            if (payload) onChatDocumentDrop(payload)
          }}
        >
          <span className="left-nav__icon" aria-hidden="true">{icon}</span>
          {!collapsed && <span className="left-nav__label">{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}
