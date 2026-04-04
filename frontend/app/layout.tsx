import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GuruBuster",
  description: "Rating the accuracy of expert forecasts",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Metal+Mania&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-gray-900 text-white shadow-lg">
          <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:px-8">
            <div className="relative flex items-center justify-center">
              <a href="/" className="flex items-center gap-3 hover:opacity-90">
                <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-red-600 font-bold text-white text-xl"
                  style={{ fontFamily: "'Metal Mania', cursive", letterSpacing: "0.1em" }}>
                  GB
                </div>
                <div>
                  <span
                    className="text-4xl tracking-wide text-white"
                    style={{ fontFamily: "'Metal Mania', cursive" }}
                  >
                    GuruBuster
                  </span>
                  <p className="text-xs text-gray-400 leading-none mt-0.5">
                    Rating the accuracy of expert forecasts
                  </p>
                </div>
              </a>
              <nav className="absolute right-0 flex items-center gap-4 text-sm">
                <a href="/" className="text-gray-300 hover:text-white transition-colors">
                  Analysts
                </a>
                <a
                  href="/admin"
                  className="rounded-md bg-red-600 px-3 py-1.5 font-medium text-white hover:bg-red-700 transition-colors"
                >
                  Admin
                </a>
              </nav>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
        <footer className="mt-16 border-t border-gray-200 bg-white py-6 text-center text-sm text-gray-400">
          GuruBuster — tracking expert accuracy
        </footer>
      </body>
    </html>
  );
}
