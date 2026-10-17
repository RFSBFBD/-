import type { Metadata } from "next";

import SiteHeader from "@/components/SiteHeader";
import { hasSupabaseConfig } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Study Platform",
  description: "A subject-isolated AI study workspace."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const supabaseEnabled = hasSupabaseConfig();

  return (
    <html lang="ar" dir="rtl">
      <body>
        <SiteHeader supabaseEnabled={supabaseEnabled} />
        {children}
      </body>
    </html>
  );
}
