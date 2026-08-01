import type { Metadata } from "next";
import React from "react";

export const metadata: Metadata = {
  title: "Walsh — Multi-Agent Trading Research",
  description: "Live demo of the Walsh multi-agent trading research pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "'Inter', system-ui, sans-serif", background: "#09090e", color: "#e2e8f0", minHeight: "100vh", WebkitFontSmoothing: "antialiased", MozOsxFontSmoothing: "grayscale" } as React.CSSProperties}>
        {children}
      </body>
    </html>
  );
}
