import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RoxStar AI Voice Room Assistant",
  description: "Real conversations. Real voices. More human. Multi-user AI voice room powered by Roxstar AI Dost & AI Sathi.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-slate-100 min-h-screen antialiased selection:bg-purple-600/30 selection:text-purple-200">
        <div className="fixed inset-0 pointer-events-none ambient-glow-purple" />
        <div className="fixed inset-0 pointer-events-none ambient-glow-pink" />
        <div className="relative z-10 flex h-screen w-full overflow-hidden">
          {children}
        </div>
      </body>
    </html>
  );
}
