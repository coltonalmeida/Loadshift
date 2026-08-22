import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, Saira_Condensed } from "next/font/google";
import "./globals.css";

const saira = Saira_Condensed({
  weight: ["600", "700"], subsets: ["latin"], variable: "--font-saira",
});
const archivo = Archivo({
  weight: ["400", "500", "600"], subsets: ["latin"], variable: "--font-archivo",
});
const plexMono = IBM_Plex_Mono({
  weight: ["400", "500"], subsets: ["latin"], variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Loadshift — run it when the grid is clean",
  description:
    "24-hour forecast of Ontario's marginal carbon intensity. Your appliance doesn't emit the grid average — it emits whatever turns on because of it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${saira.variable} ${archivo.variable} ${plexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
