import { NextAuthOptions } from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId:     process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],

  callbacks: {
    async jwt({ token, account }) {
      // account is only present on first sign-in — sync with backend then
      if (account) {
        try {
          const res = await fetch(`${BACKEND_URL}/api/v1/users/sync`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
              email:      token.email,
              name:       token.name,
              avatar_url: token.picture,
            }),
          })
          if (res.ok) {
            const data = await res.json()
            token.backendToken = data.access_token
            token.tier         = data.tier
          }
        } catch (e) {
          console.error('[NextAuth] Backend sync failed:', e)
        }
      }
      return token
    },

    async session({ session, token }) {
      session.backendToken  = (token.backendToken as string) ?? ''
      session.user.tier     = (token.tier as string) ?? 'free'
      return session
    },
  },

  pages: {
    signIn: '/login',
  },

  session: { strategy: 'jwt' },
}
