'use client'

import { useEffect, useState, useCallback } from 'react'
import { useSession } from 'next-auth/react'
import Image from 'next/image'
import {
  Users, Crown, IndianRupee, MessageSquare, Trash2,
  ArrowUp, ArrowDown, Search, RefreshCw, ShieldCheck,
  ShoppingBag, Bell, TrendingUp, Calendar, ChevronLeft, ChevronRight,
  Download, BarChart2, ExternalLink, UserCheck, UserX, Settings,
} from 'lucide-react'
import {
  getAdminStats, getAdminUsers, updateUserTier, deleteUser,
  getAdminGrowth, getAdminAlerts, deleteAdminAlert, updateUserAdmin,
  updateAppSettings,
} from '@/lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Stats {
  total_users: number
  premium_users: number
  free_users: number
  mrr: number
  new_today: number
  new_this_week: number
  chats_today: number
  occasion_today: number
  total_wishlist: number
  total_alerts: number
}

interface AdminUser {
  id: string
  email: string
  name: string
  avatar_url: string
  tier: string
  is_admin: boolean
  created_at: string | null
  chats_today: number
  occasions_today: number
  wishlist_count: number
}

interface GrowthPoint {
  date: string
  count: number
}

interface PriceAlert {
  id: number
  email: string
  title: string
  product_url: string
  image_url: string
  last_price: number | null
  currency: string
  source_site: string
  created_at: string | null
  last_checked: string | null
}

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, icon: Icon, color,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm flex items-start gap-4">
      <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-bold text-gray-900 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

// ── Tier Badge ────────────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: string }) {
  return tier === 'premium' ? (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
      <Crown className="h-3 w-3" /> Premium
    </span>
  ) : (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600">
      Free
    </span>
  )
}

// ── Growth Bar Chart ──────────────────────────────────────────────────────────

function GrowthChart({ data }: { data: GrowthPoint[] }) {
  const [hovered, setHovered] = useState<number | null>(null)
  const last14 = data.slice(-14)
  const maxCount = Math.max(...last14.map(d => d.count), 1)

  const fmt = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">User Growth</h3>
          <p className="text-xs text-gray-400 mt-0.5">New signups — last 14 days</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <BarChart2 className="h-3.5 w-3.5" />
          <span>Daily</span>
        </div>
      </div>

      <div className="flex items-end gap-1.5 h-28">
        {last14.map((d, i) => {
          const pct = maxCount === 0 ? 0 : (d.count / maxCount) * 100
          const isHovered = hovered === i
          return (
            <div
              key={d.date}
              className="flex-1 flex flex-col items-center gap-1 cursor-default"
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            >
              {isHovered && (
                <div className="bg-gray-900 text-white text-[10px] rounded px-1.5 py-0.5 whitespace-nowrap">
                  {d.count} user{d.count !== 1 ? 's' : ''}
                </div>
              )}
              <div className="w-full flex items-end" style={{ height: '80px' }}>
                <div
                  className={`w-full rounded-t-sm transition-all duration-150 ${isHovered ? 'bg-blue-500' : 'bg-blue-200'}`}
                  style={{ height: `${Math.max(pct, d.count > 0 ? 6 : 2)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>

      <div className="flex items-end gap-1.5 mt-1">
        {last14.map((d, i) => (
          <div key={d.date} className="flex-1 text-center">
            {i % 2 === 0 && (
              <span className="text-[9px] text-gray-400 leading-none">{fmt(d.date)}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type Tab = 'overview' | 'alerts' | 'settings'

export default function AdminPage() {
  const { data: session } = useSession()
  const token = session?.backendToken ?? ''

  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [stats, setStats] = useState<Stats | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [tierFilter, setTierFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [usersLoading, setUsersLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [tierConfirm, setTierConfirm] = useState<{ userId: string; name: string; email: string; currentTier: string } | null>(null)
  const [adminConfirm, setAdminConfirm] = useState<{ userId: string; name: string; email: string; currentIsAdmin: boolean } | null>(null)
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)

  // Growth chart
  const [growth, setGrowth] = useState<GrowthPoint[]>([])

  // Alerts tab
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [alertsTotal, setAlertsTotal] = useState(0)
  const [alertsPages, setAlertsPages] = useState(1)
  const [alertsPage, setAlertsPage] = useState(1)
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [alertDeleteConfirm, setAlertDeleteConfirm] = useState<number | null>(null)

  // Settings tab
  const [priceInput, setPriceInput] = useState<string>('')
  const [priceLoading, setPriceLoading] = useState(false)

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  const loadStats = useCallback(async () => {
    if (!token) return
    try { setStats(await getAdminStats(token)) } catch { showToast('Failed to load stats', false) }
  }, [token])

  const loadUsers = useCallback(async () => {
    if (!token) return
    setUsersLoading(true)
    try {
      const data = await getAdminUsers(token, { page, limit: 15, search: search || undefined, tier: tierFilter || undefined })
      setUsers(data.users); setTotal(data.total); setPages(data.pages)
    } catch { showToast('Failed to load users', false) }
    finally { setUsersLoading(false) }
  }, [token, page, search, tierFilter])

  const loadGrowth = useCallback(async () => {
    if (!token) return
    try { setGrowth(await getAdminGrowth(token, 30)) } catch { /* non-critical */ }
  }, [token])

  const loadAlerts = useCallback(async () => {
    if (!token) return
    setAlertsLoading(true)
    try {
      const data = await getAdminAlerts(token, { page: alertsPage, limit: 20 })
      setAlerts(data.alerts); setAlertsTotal(data.total); setAlertsPages(data.pages)
    } catch { showToast('Failed to load alerts', false) }
    finally { setAlertsLoading(false) }
  }, [token, alertsPage])

  // Initial load
  useEffect(() => {
    if (!token) return
    setLoading(true)
    Promise.all([loadStats(), loadUsers(), loadGrowth()]).finally(() => setLoading(false))
  }, [token, loadStats, loadUsers, loadGrowth])

  // Load alerts when switching to that tab
  useEffect(() => {
    if (activeTab === 'alerts' && token) loadAlerts()
  }, [activeTab, loadAlerts, token])

  // Tier toggle
  const handleTierChange = async (userId: string, currentTier: string) => {
    const newTier = currentTier === 'premium' ? 'free' : 'premium'
    setActionLoading(userId)
    try {
      await updateUserTier(token, userId, newTier)
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, tier: newTier } : u))
      await loadStats()
      showToast(`User ${newTier === 'premium' ? 'upgraded to Premium' : 'downgraded to Free'}`)
    } catch { showToast('Failed to update tier', false) }
    finally { setActionLoading(null) }
  }

  // Delete user
  const handleDelete = async (userId: string) => {
    setActionLoading(userId)
    try {
      await deleteUser(token, userId)
      setUsers(prev => prev.filter(u => u.id !== userId))
      setTotal(prev => prev - 1)
      await loadStats()
      showToast('User deleted successfully')
    } catch { showToast('Failed to delete user', false) }
    finally { setActionLoading(null); setDeleteConfirm(null) }
  }

  // Toggle admin
  const handleAdminToggle = async (userId: string, currentIsAdmin: boolean) => {
    setActionLoading(userId)
    try {
      await updateUserAdmin(token, userId, !currentIsAdmin)
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: !currentIsAdmin } : u))
      showToast(currentIsAdmin ? 'Admin access removed' : 'User promoted to admin')
    } catch { showToast('Failed to update admin status', false) }
    finally { setActionLoading(null) }
  }

  // Delete alert
  const handleDeleteAlert = async (alertId: number) => {
    try {
      await deleteAdminAlert(token, alertId)
      setAlerts(prev => prev.filter(a => a.id !== alertId))
      setAlertsTotal(prev => prev - 1)
      await loadStats()
      showToast('Alert deleted')
    } catch { showToast('Failed to delete alert', false) }
    finally { setAlertDeleteConfirm(null) }
  }

  // Save subscription price
  const handleSavePrice = async () => {
    const price = parseInt(priceInput)
    if (!price || price < 1) { showToast('Enter a valid price', false); return }
    setPriceLoading(true)
    try {
      await updateAppSettings(token, price)
      await loadStats()
      showToast(`Subscription price updated to ₹${price}`)
      setPriceInput('')
    } catch { showToast('Failed to update price', false) }
    finally { setPriceLoading(false) }
  }

  // Export users as CSV
  const exportCSV = () => {
    const header = ['ID', 'Email', 'Name', 'Tier', 'Admin', 'Joined', 'Chats Today', 'Wishlist']
    const rows = users.map(u => [
      u.id, u.email, u.name || '', u.tier,
      u.is_admin ? 'yes' : 'no',
      u.created_at ? new Date(u.created_at).toLocaleDateString('en-IN') : '',
      u.chats_today, u.wishlist_count,
    ])
    const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `users-${new Date().toISOString().slice(0, 10)}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return '—'
    return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  const formatPrice = (price: number | null, currency: string) => {
    if (price == null) return '—'
    return currency === 'INR' ? `₹${price.toLocaleString('en-IN')}` : `${currency} ${price}`
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="h-8 w-8 text-gray-400 animate-spin" />
          <p className="text-sm text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium text-white transition-all ${toast.ok ? 'bg-emerald-500' : 'bg-red-500'}`}>
          {toast.msg}
        </div>
      )}

      {/* Delete User Confirm Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Delete User?</h3>
            <p className="text-sm text-gray-500">This permanently deletes the user and all their data. This action cannot be undone.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteConfirm(null)} className="flex-1 py-2.5 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={() => handleDelete(deleteConfirm)} disabled={actionLoading === deleteConfirm} className="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50">
                {actionLoading === deleteConfirm ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tier Change Confirm Modal */}
      {tierConfirm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm space-y-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${tierConfirm.currentTier === 'premium' ? 'bg-gray-100' : 'bg-amber-100'}`}>
                {tierConfirm.currentTier === 'premium'
                  ? <ArrowDown className="h-5 w-5 text-gray-500" />
                  : <Crown className="h-5 w-5 text-amber-500" />}
              </div>
              <h3 className="text-lg font-semibold text-gray-900">
                {tierConfirm.currentTier === 'premium' ? 'Downgrade to Free?' : 'Upgrade to Premium?'}
              </h3>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-800">{tierConfirm.name || tierConfirm.email}</p>
              <p className="text-xs text-gray-400">{tierConfirm.email}</p>
            </div>
            <p className="text-sm text-gray-500">
              {tierConfirm.currentTier === 'premium'
                ? 'This user will lose Premium access and be reverted to the Free plan with usage limits.'
                : 'This user will get unlimited access to all Premium features immediately.'}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setTierConfirm(null)}
                className="flex-1 py-2.5 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => { handleTierChange(tierConfirm.userId, tierConfirm.currentTier); setTierConfirm(null) }}
                disabled={actionLoading === tierConfirm.userId}
                className={`flex-1 py-2.5 rounded-xl text-white text-sm font-medium disabled:opacity-50 ${
                  tierConfirm.currentTier === 'premium' ? 'bg-gray-700 hover:bg-gray-800' : 'bg-amber-500 hover:bg-amber-600'
                }`}
              >
                {tierConfirm.currentTier === 'premium' ? 'Downgrade to Free' : 'Upgrade to Premium'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Admin Toggle Confirm Modal */}
      {adminConfirm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm space-y-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${adminConfirm.currentIsAdmin ? 'bg-red-100' : 'bg-blue-100'}`}>
                {adminConfirm.currentIsAdmin
                  ? <UserX className="h-5 w-5 text-red-500" />
                  : <UserCheck className="h-5 w-5 text-blue-500" />}
              </div>
              <h3 className="text-lg font-semibold text-gray-900">
                {adminConfirm.currentIsAdmin ? 'Remove Admin Access?' : 'Make Admin?'}
              </h3>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-800">{adminConfirm.name || adminConfirm.email}</p>
              <p className="text-xs text-gray-400">{adminConfirm.email}</p>
            </div>
            <p className="text-sm text-gray-500">
              {adminConfirm.currentIsAdmin
                ? 'This user will lose access to the admin dashboard immediately.'
                : 'This user will gain full access to the admin dashboard, including the ability to manage other users.'}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setAdminConfirm(null)}
                className="flex-1 py-2.5 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => { handleAdminToggle(adminConfirm.userId, adminConfirm.currentIsAdmin); setAdminConfirm(null) }}
                disabled={actionLoading === adminConfirm.userId}
                className={`flex-1 py-2.5 rounded-xl text-white text-sm font-medium disabled:opacity-50 ${
                  adminConfirm.currentIsAdmin ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-600 hover:bg-blue-700'
                }`}
              >
                {adminConfirm.currentIsAdmin ? 'Remove Admin' : 'Make Admin'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Alert Confirm Modal */}
      {alertDeleteConfirm !== null && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Delete Alert?</h3>
            <p className="text-sm text-gray-500">This permanently removes this price alert. The user will no longer receive price drop notifications for it.</p>
            <div className="flex gap-3">
              <button onClick={() => setAlertDeleteConfirm(null)} className="flex-1 py-2.5 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={() => handleDeleteAlert(alertDeleteConfirm)} className="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="bg-white border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gray-900 flex items-center justify-center">
              <ShieldCheck className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900">Fashion Finder</h1>
              <p className="text-xs text-gray-400">Admin Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 hidden sm:block">{session?.user?.email}</span>
            <button
              onClick={() => { loadStats(); loadUsers(); loadGrowth(); if (activeTab === 'alerts') loadAlerts() }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6 border-t border-gray-100">
            {(['overview', 'alerts', 'settings'] as Tab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'border-gray-900 text-gray-900'
                    : 'border-transparent text-gray-400 hover:text-gray-600'
                }`}
              >
                {tab === 'alerts'
                  ? `Price Alerts${alertsTotal > 0 ? ` (${alertsTotal})` : stats ? ` (${stats.total_alerts})` : ''}`
                  : tab === 'settings' ? 'Settings' : 'Overview'}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* ── Overview Tab ── */}
        {activeTab === 'overview' && (
          <>
            {/* Stats Grid */}
            {stats && (
              <div>
                <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Overview</h2>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                  <StatCard label="Total Users"   value={stats.total_users}    sub={`+${stats.new_today} today`}           icon={Users}         color="bg-blue-500" />
                  <StatCard label="Premium"        value={stats.premium_users}  sub={`${stats.free_users} free`}            icon={Crown}         color="bg-amber-500" />
                  <StatCard label="MRR"            value={`₹${stats.mrr.toLocaleString('en-IN')}`} sub="monthly revenue"  icon={IndianRupee}   color="bg-emerald-500" />
                  <StatCard label="Chats Today"    value={stats.chats_today}    sub={`${stats.occasion_today} occasions`}  icon={MessageSquare} color="bg-purple-500" />
                  <StatCard label="New This Week"  value={stats.new_this_week}  sub={`${stats.total_alerts} alerts active`} icon={TrendingUp}   color="bg-rose-500" />
                </div>

                {/* Secondary stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                  <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm flex items-center gap-3">
                    <ShoppingBag className="h-4 w-4 text-gray-400" />
                    <div><p className="text-xs text-gray-500">Wishlist Items</p><p className="text-lg font-bold text-gray-800">{stats.total_wishlist.toLocaleString()}</p></div>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm flex items-center gap-3">
                    <Bell className="h-4 w-4 text-gray-400" />
                    <div><p className="text-xs text-gray-500">Price Alerts</p><p className="text-lg font-bold text-gray-800">{stats.total_alerts.toLocaleString()}</p></div>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm flex items-center gap-3">
                    <Calendar className="h-4 w-4 text-gray-400" />
                    <div><p className="text-xs text-gray-500">New Today</p><p className="text-lg font-bold text-gray-800">{stats.new_today}</p></div>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm flex items-center gap-3">
                    <Crown className="h-4 w-4 text-gray-400" />
                    <div>
                      <p className="text-xs text-gray-500">Conversion</p>
                      <p className="text-lg font-bold text-gray-800">
                        {stats.total_users > 0 ? `${Math.round((stats.premium_users / stats.total_users) * 100)}%` : '0%'}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Growth Chart */}
            {growth.length > 0 && <GrowthChart data={growth} />}

            {/* Users Table */}
            <div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Users</h2>
                  <p className="text-sm text-gray-500 mt-0.5">{total.toLocaleString()} total</p>
                </div>
                <div className="flex items-center gap-2">
                  {/* Search */}
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                    <input
                      value={search}
                      onChange={e => { setSearch(e.target.value); setPage(1) }}
                      placeholder="Search email or name..."
                      className="pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-gray-200 w-52"
                    />
                  </div>
                  {/* Tier filter */}
                  <select
                    value={tierFilter}
                    onChange={e => { setTierFilter(e.target.value); setPage(1) }}
                    className="px-3 py-2 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-gray-200"
                  >
                    <option value="">All tiers</option>
                    <option value="free">Free</option>
                    <option value="premium">Premium</option>
                  </select>
                  {/* Export CSV */}
                  <button
                    onClick={exportCSV}
                    disabled={users.length === 0}
                    title="Export current page as CSV"
                    className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-xl bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                  >
                    <Download className="h-3.5 w-3.5" /> CSV
                  </button>
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                {usersLoading ? (
                  <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 text-gray-300 animate-spin" /></div>
                ) : users.length === 0 ? (
                  <div className="text-center py-16 text-sm text-gray-400">No users found</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-100 bg-gray-50/50">
                          <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">User</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Tier</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide hidden md:table-cell">Joined</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide hidden lg:table-cell">Activity</th>
                          <th className="text-right px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {users.map(user => (
                          <tr key={user.id} className="hover:bg-gray-50/50 transition-colors">
                            <td className="px-5 py-3.5">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full overflow-hidden bg-gray-100 flex-shrink-0">
                                  {user.avatar_url ? (
                                    <Image src={user.avatar_url} alt={user.name} width={32} height={32} className="object-cover" />
                                  ) : (
                                    <div className="w-full h-full flex items-center justify-center text-xs font-bold text-gray-400">
                                      {user.email[0].toUpperCase()}
                                    </div>
                                  )}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-medium text-gray-900 truncate max-w-[180px]">
                                    {user.name || '—'}
                                    {user.is_admin && (
                                      <span className="ml-1.5 inline-flex items-center gap-0.5 text-[10px] text-blue-600 font-semibold">
                                        <ShieldCheck className="h-2.5 w-2.5" /> Admin
                                      </span>
                                    )}
                                  </p>
                                  <p className="text-xs text-gray-400 truncate max-w-[180px]">{user.email}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-5 py-3.5"><TierBadge tier={user.tier} /></td>
                            <td className="px-5 py-3.5 hidden md:table-cell">
                              <span className="text-sm text-gray-500">{formatDate(user.created_at)}</span>
                            </td>
                            <td className="px-5 py-3.5 hidden lg:table-cell">
                              <div className="flex items-center gap-3 text-xs text-gray-500">
                                <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" /> {user.chats_today}</span>
                                <span className="flex items-center gap-1"><ShoppingBag className="h-3 w-3" /> {user.wishlist_count}</span>
                              </div>
                            </td>
                            <td className="px-5 py-3.5">
                              <div className="flex items-center justify-end gap-2">
                                {/* Tier toggle — only for non-admins */}
                                {!user.is_admin && (
                                  <button
                                    onClick={() => setTierConfirm({ userId: user.id, name: user.name, email: user.email, currentTier: user.tier })}
                                    disabled={actionLoading === user.id}
                                    title={user.tier === 'premium' ? 'Downgrade to Free' : 'Upgrade to Premium'}
                                    className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                                      user.tier === 'premium'
                                        ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                                        : 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                                    }`}
                                  >
                                    {user.tier === 'premium'
                                      ? <><ArrowDown className="h-3 w-3" /> Free</>
                                      : <><ArrowUp className="h-3 w-3" /> Premium</>}
                                  </button>
                                )}
                                {/* Admin toggle — for everyone except self */}
                                {user.email !== session?.user?.email && (
                                  <button
                                    onClick={() => setAdminConfirm({ userId: user.id, name: user.name, email: user.email, currentIsAdmin: user.is_admin })}
                                    disabled={actionLoading === user.id}
                                    title={user.is_admin ? 'Remove admin access' : 'Make admin'}
                                    className={`p-1.5 rounded-lg transition-colors disabled:opacity-50 ${
                                      user.is_admin
                                        ? 'text-blue-500 hover:text-blue-700 hover:bg-blue-50'
                                        : 'text-gray-400 hover:text-blue-500 hover:bg-blue-50'
                                    }`}
                                  >
                                    {user.is_admin ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                                  </button>
                                )}
                                {/* Delete — only for non-admins */}
                                {!user.is_admin && (
                                  <button
                                    onClick={() => setDeleteConfirm(user.id)}
                                    disabled={actionLoading === user.id}
                                    title="Delete user"
                                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                {/* Self label */}
                                {user.email === session?.user?.email && (
                                  <span className="text-xs text-gray-400 italic">You</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Pagination */}
                {pages > 1 && (
                  <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
                    <p className="text-xs text-gray-400">Page {page} of {pages} · {total} users</p>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
                        <ChevronLeft className="h-4 w-4" />
                      </button>
                      <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page === pages} className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {/* ── Price Alerts Tab ── */}
        {activeTab === 'alerts' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Price Alerts</h2>
                <p className="text-sm text-gray-500 mt-0.5">{alertsTotal.toLocaleString()} active alerts</p>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              {alertsLoading ? (
                <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 text-gray-300 animate-spin" /></div>
              ) : alerts.length === 0 ? (
                <div className="text-center py-16 text-sm text-gray-400">No active price alerts</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-100 bg-gray-50/50">
                        <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Product</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide hidden sm:table-cell">User</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide hidden md:table-cell">Price</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide hidden lg:table-cell">Added</th>
                        <th className="text-right px-5 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {alerts.map(alert => (
                        <tr key={alert.id} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-5 py-3.5">
                            <div className="flex items-center gap-3">
                              {alert.image_url ? (
                                <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0">
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img src={alert.image_url} alt={alert.title} className="w-full h-full object-cover" />
                                </div>
                              ) : (
                                <div className="w-10 h-10 rounded-lg bg-gray-100 flex-shrink-0 flex items-center justify-center">
                                  <Bell className="h-4 w-4 text-gray-300" />
                                </div>
                              )}
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-gray-900 truncate max-w-[200px]">{alert.title}</p>
                                <a
                                  href={alert.product_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs text-blue-500 hover:underline flex items-center gap-0.5 truncate max-w-[200px]"
                                >
                                  {alert.source_site || 'View product'} <ExternalLink className="h-2.5 w-2.5 flex-shrink-0" />
                                </a>
                              </div>
                            </div>
                          </td>
                          <td className="px-5 py-3.5 hidden sm:table-cell">
                            <span className="text-sm text-gray-600 truncate max-w-[160px] block">{alert.email}</span>
                          </td>
                          <td className="px-5 py-3.5 hidden md:table-cell">
                            <span className="text-sm font-medium text-gray-800">{formatPrice(alert.last_price, alert.currency)}</span>
                          </td>
                          <td className="px-5 py-3.5 hidden lg:table-cell">
                            <span className="text-sm text-gray-500">{formatDate(alert.created_at)}</span>
                          </td>
                          <td className="px-5 py-3.5">
                            <div className="flex justify-end">
                              <button
                                onClick={() => setAlertDeleteConfirm(alert.id)}
                                title="Delete alert"
                                className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Alerts Pagination */}
              {alertsPages > 1 && (
                <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
                  <p className="text-xs text-gray-400">Page {alertsPage} of {alertsPages} · {alertsTotal} alerts</p>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setAlertsPage(p => Math.max(1, p - 1))} disabled={alertsPage === 1} className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button onClick={() => setAlertsPage(p => Math.min(alertsPages, p + 1))} disabled={alertsPage === alertsPages} className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Settings Tab ── */}
        {activeTab === 'settings' && (
          <div className="max-w-lg space-y-6">
            <div>
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Settings</h2>
              <p className="text-sm text-gray-500">Changes apply everywhere — pricing page, chat, try-on, and profile card.</p>
            </div>

            {/* Subscription Price */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
                  <IndianRupee className="h-4 w-4 text-emerald-600" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900">Subscription Price</p>
                  <p className="text-xs text-gray-400">
                    Current: ₹{stats ? Math.round(stats.mrr / Math.max(stats.premium_users, 1)) : '—'}/month
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400 font-medium">₹</span>
                  <input
                    type="number"
                    min={1}
                    value={priceInput}
                    onChange={e => setPriceInput(e.target.value)}
                    placeholder="Enter new price"
                    className="w-full pl-7 pr-3 py-2.5 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-200"
                  />
                </div>
                <button
                  onClick={handleSavePrice}
                  disabled={priceLoading || !priceInput}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 transition-colors"
                >
                  {priceLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Settings className="h-3.5 w-3.5" />}
                  Save
                </button>
              </div>

              <p className="text-xs text-gray-400">
                This updates the price shown on the pricing page, chat upgrade prompts, virtual try-on gate, and profile menu. It does <strong>not</strong> change your Razorpay plan — update the plan amount in the Razorpay dashboard separately.
              </p>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
