import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Tennis Coach",
  description: "Upload a tennis video for AI-powered coaching feedback",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        {children}
      </body>
    </html>
  );
}
