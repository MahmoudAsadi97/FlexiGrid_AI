import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlexiGrid AI — Evidence-grounded energy planning",
  description:
    "A multi-agent RAG and MCP prototype that creates explainable household energy schedules using Elia grid data.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
