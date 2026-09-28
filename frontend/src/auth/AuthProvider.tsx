import type { Session } from '@supabase/supabase-js'
import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { isSupabaseConfigured, supabase } from '../lib/supabase'
import { AuthContext, type AuthContextValue } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(isSupabaseConfigured)

  useEffect(() => {
    if (!supabase) {
      return
    }

    void supabase.auth.getSession()
      .then(({ data }) => {
        setSession(data.session)
      })
      .finally(() => setLoading(false))

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })

    return () => data.subscription.unsubscribe()
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      configured: isSupabaseConfigured,
      loading,
      session,
      user: session?.user ?? null,
      signIn: async (email: string, password: string) => {
        if (!supabase) throw new Error('Supabase is not configured.')

        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        })

        if (error) throw error
      },
      signUp: async (input) => {
        if (!supabase) throw new Error('Supabase is not configured.')

        const { data, error } = await supabase.auth.signUp({
          email: input.email,
          password: input.password,
          options: {
            data: {
              greensmecapt_requested_role: input.role,
              company_name: input.companyName,
              company_sector: input.companySector,
              company_jurisdiction: input.companyJurisdiction,
            },
          },
        })

        if (error) throw error
        if (data.session) await supabase.auth.refreshSession()
        return { requiresEmailConfirmation: data.session === null }
      },
      requestPasswordReset: async (email: string) => {
        if (!supabase) throw new Error('Supabase is not configured.')

        const { error } = await supabase.auth.resetPasswordForEmail(
          email,
          {
            redirectTo: `${window.location.origin}/settings`,
          },
        )

        if (error) throw error
      },
      updatePassword: async (password: string) => {
        if (!supabase) throw new Error('Supabase is not configured.')

        const { error } = await supabase.auth.updateUser({
          password,
        })

        if (error) throw error
      },
      signOut: async () => {
        if (!supabase) return
        const { error } = await supabase.auth.signOut()
        if (error) throw error
      },
    }),
    [loading, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
