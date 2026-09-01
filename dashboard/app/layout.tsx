import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Independent analysis of AI",
  description: "Understand the AI landscape to choose the best model and provider for your use case",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
