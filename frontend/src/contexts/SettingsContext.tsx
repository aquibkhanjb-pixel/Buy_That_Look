'use client'

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { getAppSettings } from '@/lib/api'

interface AppSettings {
  subscriptionPrice: number
}

const SettingsContext = createContext<AppSettings>({ subscriptionPrice: 25 })

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>({ subscriptionPrice: 25 })

  useEffect(() => {
    getAppSettings()
      .then(data => setSettings({ subscriptionPrice: Number(data.subscription_price) || 25 }))
      .catch(() => {})
  }, [])

  return (
    <SettingsContext.Provider value={settings}>
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  return useContext(SettingsContext)
}
