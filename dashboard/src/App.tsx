import { useState } from "react";
import OverviewPage from "./pages/OverviewPage";
import DevicePage from "./pages/DevicePage";

type Page = "overview" | "device";

export default function App() {
  const [page, setPage] = useState<Page>("overview");

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200 flex flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between px-6 h-13 bg-[#1a1f2e] border-b border-[#2d3347]">
        <span className="font-bold text-[15px] tracking-tight">
          AWARE Dashboard
        </span>
        <nav className="flex gap-1">
          {(["overview", "device"] as Page[]).map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer border-none
                ${
                  page === p
                    ? "bg-[#2d3347] text-slate-200"
                    : "bg-transparent text-slate-500 hover:bg-[#2d3347] hover:text-slate-200"
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
