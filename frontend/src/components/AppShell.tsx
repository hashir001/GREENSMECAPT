import {
  BarChart3,
  Building2,
  ChevronDown,
  FileSearch,
  Landmark,
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
import { usePermissions } from '../auth/usePermissions'
import { isPreviewMode } from '../lib/supabase'
import type { ApplicationRole } from '../types/api'
import { Brand } from './Brand'

const navigation = [
  { label: 'Overview', path: '/', icon: LayoutDashboard, roles: ['admin', 'reviewer', 'expert', 'investor', 'sme_user'] },
  { label: 'SME portfolio', path: '/companies', icon: Building2, roles: ['admin', 'reviewer', 'investor', 'sme_user'] },
  { label: 'Assessments', path: '/assessments', icon: BarChart3, roles: ['admin', 'reviewer', 'investor'] },
  { label: 'Evidence review', path: '/evidence', icon: FileSearch, roles: ['admin', 'reviewer'] },
  { label: 'Financials', path: '/financial', icon: Landmark, roles: ['admin', 'reviewer', 'sme_user'] },
]

function roleLabel(role: unknown): string {
  if (typeof role !== 'string') return 'Platform user'
  return role.replaceAll('_', ' ')
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth()
  const { canReviewEvidence, role: applicationRole } = usePermissions()
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
          {navigation
            .filter(({ roles }) => (
              applicationRole !== null
              && (roles as ApplicationRole[]).includes(applicationRole)
            ))
            .map(({ label, path, icon: Icon }) => (
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
          <NavLink
            className={({ isActive }) =>
              `nav-item ${isActive ? 'nav-item--active' : ''}`
            }
            to="/settings"
            onClick={() => setMobileOpen(false)}
          >
            <Settings size={19} />
            <span>Settings</span>
          </NavLink>
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
            {canReviewEvidence && (
              <NavLink className="icon-button" to="/evidence" aria-label="Open evidence review queue">
                <FileSearch size={18} />
              </NavLink>
            )}
            <NavLink className="user-menu" to="/settings">
              <span className="user-menu__avatar">
                {isPreviewMode ? 'P' : email.charAt(0).toUpperCase()}
              </span>
              <span className="user-menu__copy">
                <strong>{isPreviewMode ? 'Preview reviewer' : email}</strong>
                <small>{isPreviewMode ? 'interactive demo' : role}</small>
              </span>
              <ChevronDown size={16} />
            </NavLink>
          </div>
        </header>

        <main className="page-container">{children}</main>
      </div>
    </div>
  )
}
