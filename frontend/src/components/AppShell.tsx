import {
  BarChart3,
  Bell,
  Building2,
  ChevronDown,
  FileSearch,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { isPreviewMode } from '../lib/supabase'
import { Brand } from './Brand'

const navigation = [
  { label: 'Overview', path: '/', icon: LayoutDashboard },
  { label: 'SME portfolio', path: '/companies', icon: Building2 },
  { label: 'Assessments', path: '/assessments', icon: BarChart3 },
  { label: 'Evidence review', path: '/evidence', icon: FileSearch },
]

function roleLabel(role: unknown): string {
  if (typeof role !== 'string') return 'Platform user'
  return role.replaceAll('_', ' ')
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const role = roleLabel(user?.app_metadata.greensmecapt_role)
  const email = user?.email ?? 'Authenticated user'

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__brand-row">
          <Brand />
          <button
            className="icon-button sidebar__close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        <div className="sidebar__eyebrow">Investment intelligence</div>

        <nav className="sidebar__nav" aria-label="Primary navigation">
          {navigation.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'nav-item--active' : ''}`
              }
            >
              <Icon size={19} strokeWidth={1.9} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__trust-card">
          <ShieldCheck size={20} />
          <div>
            <strong>Evidence protected</strong>
            <span>Traceable, validated and access controlled</span>
          </div>
        </div>

        <div className="sidebar__bottom">
          <button className="nav-item" type="button">
            <Settings size={19} />
            <span>Settings</span>
          </button>
          <button
            className="nav-item"
            type="button"
            onClick={() => void signOut()}
          >
            <LogOut size={19} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className="app-main">
        <header className="topbar">
          <button
            className="icon-button topbar__menu"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={21} />
          </button>

          <div className="topbar__status">
            <span className="live-dot" />
            {isPreviewMode ? 'Presentation preview' : 'Platform operational'}
          </div>

          <div className="topbar__actions">
            <button className="icon-button" type="button" aria-label="Notifications">
              <Bell size={19} />
              <span className="notification-dot" />
            </button>
            <div className="user-menu">
              <span className="user-menu__avatar">
                {isPreviewMode ? 'P' : email.charAt(0).toUpperCase()}
              </span>
              <span className="user-menu__copy">
                <strong>{isPreviewMode ? 'Preview reviewer' : email}</strong>
                <small>{isPreviewMode ? 'interactive demo' : role}</small>
              </span>
              <ChevronDown size={16} />
            </div>
          </div>
        </header>

        <main className="page-container">{children}</main>
      </div>
    </div>
  )
}
