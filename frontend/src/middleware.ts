export { default } from 'next-auth/middleware'

export const config = {
  // Protect every route except: login page, NextAuth API, Next.js internals
  matcher: ['/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)'],
}
