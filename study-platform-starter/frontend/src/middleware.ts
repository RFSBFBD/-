import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

const isProtectedRoute = (pathname: string) =>
  pathname.startsWith("/dashboard") || pathname.startsWith("/subjects");

export async function middleware(request: NextRequest) {
  const supabaseEnabled = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
  );

  if (!supabaseEnabled) {
    return NextResponse.next();
  }

  const response = await updateSession(request);
  const { pathname } = request.nextUrl;

  if (isProtectedRoute(pathname)) {
    // The session cookie is refreshed above; redirect to sign-in is handled
    // by the page-level server component using getUser().
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)"
  ]
};
