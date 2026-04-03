import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prediction Tracker",
  description: "Rating the accuracy of expert forecasts",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-gray-900 text-white shadow-lg">
          <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between">
              <a href="/" className="flex items-center gap-3 hover:opacity-90">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500 font-bold text-white text-sm">
                  PT
                </div>
                <div>
                  <span className="text-lg font-bold tracking-tight">Prediction Tracker</span>
                  <p className="text-xs text-gray-400 leading-none mt-0.5">
                    Rating the accuracy of expert forecasts
                  </p>
                </div>
              </a>
              <nav className="flex items-center gap-4 text-sm">
                <a href="/" className="text-gray-300 hover:text-white transition-colors">
                  Analysts
                </a>
                <a
                  href="/admin"
                  className="rounded-md bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  Admin
                </a>
              </nav>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
        <footer className="mt-16 border-t border-gray-200 bg-white py-6 text-center text-sm text-gray-400">
          Prediction Tracker — tracking expert accuracy
        </footer>
      </body>
    </html>
  );
}
