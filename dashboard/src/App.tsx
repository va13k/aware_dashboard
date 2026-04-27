import { useState } from "react";
import OverviewPage from "./pages/OverviewPage";
import DevicePage from "./pages/DevicePage";

type Page = "overview" | "device";

export default function App() {
  const [page, setPage] = useState<Page>("overview");

  return (
    <div className="min-h-screen bg-page text-ink font-sans flex flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between px-6 h-13 bg-card backdrop-blur-xl border-b border-wire">
        <span className="font-bold text-[15px] tracking-tight">
          AWARE Dashboard
        </span>
        <nav className="flex gap-1">
          {(["overview", "device"] as Page[]).map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors cursor-pointer border-none
                ${
                  page === p
                    ? "bg-teal-soft text-teal"
                    : "bg-transparent text-sage hover:bg-teal-soft/50 hover:text-ink"
                }`}
            >
              {p === "overview" ? "Overview" : "Per Device"}
            </button>
          ))}
        </nav>
      </header>
      <main className="px-6 py-6 w-full max-w-350 mx-auto">
        {page === "overview" ? <OverviewPage /> : <DevicePage />}
      </main>
    </div>
  );
}
