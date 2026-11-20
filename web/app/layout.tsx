import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "ProbaFoot", description: "Analyse probabiliste de matchs de football" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <header className="top">
          <div className="wrap">
            <strong>PROBAFOOT</strong>
            <nav>
              <Link href="/">Matchs</Link>
              <Link href="/performance">Performance</Link>
              <Link href="/predict">Estimer un match</Link>
            </nav>
          </div>
        </header>
        <main className="wrap">
          <div className="banner">
            Les paris comportent des risques de perte. Ne pariez que ce que vous pouvez vous permettre de perdre.
            Probabilités estimées : aucune garantie de gain. Réservé aux majeurs.
          </div>
          {children}
        </main>
      </body>
    </html>
  );
}
