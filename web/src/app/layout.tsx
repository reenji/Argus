import type { Metadata } from "next";
import { connection } from "next/server";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "ARGUS | Command Interface",
  description: "A focused voice and text interface for ARGUS.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Nonces only exist per request, so pages render dynamically instead of at build time.
  await connection();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
