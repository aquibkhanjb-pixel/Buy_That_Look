import 'next-auth'
import 'next-auth/jwt'

declare module 'next-auth' {
  interface Session {
    backendToken: string
    user: {
      name?:  string | null
      email?: string | null
      image?: string | null
      tier:   string            // 'free' | 'premium'
    }
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    backendToken?: string
    tier?:         string
  }
}
