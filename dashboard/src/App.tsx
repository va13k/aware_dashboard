import { useState, type ReactNode } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  Link,
  useLocation,
} from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import DevicesPage from "./pages/DevicesPage";
import DeviceDetailPage from "./pages/DeviceDetailPage";
import ManifestPage from "./pages/ManifestPage";
import { HeaderSlotContext, useHeaderSlot } from "./utils/headerSlot";

function Layout() {
  const { pathname } = useLocation();
  // On a device detail route (/devices/<id> or /devices/<platform>/<id>) the
  // quick link goes back to the device list instead of the overview.
  const onDeviceDetail = /^\/devices\/[^/]+/.test(pathname);
  const backLink = onDeviceDetail
    ? { to: "/devices", label: "All devices" }
    : { to: "/", label: "Main page" };
  const { center } = useHeaderSlot();

  return (
    <div className="min-h-screen bg-page text-ink font-sans flex flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between px-6 h-13 bg-card backdrop-blur-xl border-b border-wire">
        {center ? (
          <div className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 md:block">
            {center}
          </div>
        ) : null}
        <div className="flex items-center gap-3">
          <span className="font-bold text-[15px] tracking-tight">
            AWARE Dashboard
          </span>
          <Link
            to={backLink.to}
            className="flex items-center gap-1 text-[12px] font-medium text-sage hover:text-ink transition-colors no-underline px-2.5 py-1 rounded-lg hover:bg-teal-soft/50"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path
                d="M10 12L6 8l4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {backLink.label}
          </Link>
        </div>
        <nav className="flex gap-1">
          {[
            { to: "/", label: "Overview", end: true },
            { to: "/devices", label: "Devices", end: false },
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
          <Route path="devices" element={<DevicesPage />} />
          <Route
            path="devices/:platform/:deviceId"
            element={<DeviceDetailPage />}
          />
          <Route path="devices/:deviceId" element={<DeviceDetailPage />} />
          <Route path="manifest" element={<ManifestPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [center, setCenter] = useState<ReactNode>(null);
  return (
    <BrowserRouter basename="/dashboard">
      <HeaderSlotContext.Provider value={{ center, setCenter }}>
        <Layout />
      </HeaderSlotContext.Provider>
    </BrowserRouter>
  );
}
