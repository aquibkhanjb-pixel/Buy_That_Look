'use client'

import { SessionProvider } from 'next-auth/react'
import { SettingsProvider } from '@/contexts/SettingsContext'

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <SettingsProvider>{children}</SettingsProvider>
    </SessionProvider>
  )
}
