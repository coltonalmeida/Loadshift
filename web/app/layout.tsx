import type { Metadata } from "next";
import { Bricolage_Grotesque, Instrument_Sans, Spline_Sans_Mono } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const bricolage = Bricolage_Grotesque({
  weight: ["600", "700", "800"], subsets: ["latin"], variable: "--font-bricolage",
});
const instrument = Instrument_Sans({
  weight: ["400", "500", "600"], subsets: ["latin"], variable: "--font-instrument",
});
const splineMono = Spline_Sans_Mono({
  weight: ["400", "500"], subsets: ["latin"], variable: "--font-spline-mono",
});

export const metadata: Metadata = {
  title: "Loadshift",
  description:
    "A 24-hour forecast of Ontario's marginal carbon intensity. Your appliance emits what turns on because of it, not the grid average.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${instrument.variable} ${splineMono.variable}`}
    >
      <body className="min-h-[100dvh]">
        <Nav />
        {children}
      </body>
    </html>
  );
}
