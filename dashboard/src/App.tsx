import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import DevicePage from "./pages/DevicePage";

function Layout() {
  return (
    <div className="min-h-screen bg-page text-ink font-sans flex flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between px-6 h-13 bg-card backdrop-blur-xl border-b border-wire">
        <div className="flex items-center gap-3">
          <span className="font-bold text-[15px] tracking-tight">
            AWARE Dashboard
          </span>
          <a
            href="/"
            className="flex items-center gap-1 text-[12px] font-medium text-sage hover:text-ink transition-colors no-underline px-2.5 py-1 rounded-lg hover:bg-teal-soft/50"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Main page
          </a>
        </div>
        <nav className="flex gap-1">
          {[
            { to: "/", label: "Overview", end: true },
            { to: "/devices", label: "Per Device", end: false },
          ].map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors cursor-pointer border-none no-underline ` +
                (isActive
                  ? "bg-teal-soft text-teal"
                  : "bg-transparent text-sage hover:bg-teal-soft/50 hover:text-ink")
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="px-6 py-6 w-full max-w-350 mx-auto">
        <Routes>
          <Route index element={<OverviewPage />} />
          <Route path="devices" element={<DevicePage />} />
          <Route path="devices/:platform/:deviceId" element={<DevicePage />} />
          <Route path="devices/:deviceId" element={<DevicePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename="/dashboard">
      <Layout />
    </BrowserRouter>
  );
}
