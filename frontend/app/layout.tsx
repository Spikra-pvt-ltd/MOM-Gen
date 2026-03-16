import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "sonner";

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MoM Generator — AI Minutes of Meeting",
  description:
    "Automatically generate structured Minutes of Meeting from audio and video recordings using AI.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={inter.variable}
        style={{ fontFamily: "var(--font-inter), -apple-system, sans-serif" }}
      >
        <div className="relative z-10">{children}</div>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#16162a",
              border: "1px solid rgba(139,92,246,0.3)",
              color: "#f1f0ff",
            },
          }}
        />
      </body>
    </html>
  );
}
