import type { Metadata } from "next";
import { Inter, Bebas_Neue } from "next/font/google";
import "./globals.css";

const inter = Inter({ 
  subsets: ["latin"],
  variable: '--font-inter',
});

const bebas = Bebas_Neue({
  subsets: ["latin"],
  variable: '--font-bebas',
  weight: ['400'],
});

export const metadata: Metadata = {
  title: "DataForge | AI Research",
  description: "Automated AI-driven extraction and dataset forge",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${bebas.variable} font-inter antialiased`}>
        {children}
      </body>
    </html>
  );
}
