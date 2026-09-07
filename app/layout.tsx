import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Independent benchmark data",
  description: "Compare precomputed benchmark summaries across models and providers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
