import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAsync } from "../hooks/useAsync";
import { useClock } from "../hooks/useClock";
import { ClockControl } from "./ClockControl";
import { Icon, type IconName } from "./Icon";

const LINKS: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/items", label: "Items", icon: "tool" },
  { to: "/members", label: "Members", icon: "users" },
  { to: "/overdue", label: "Overdue", icon: "alarm" },
  { to: "/outbox", label: "Outbox", icon: "message" },
];

const istDay = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  weekday: "long",
  day: "numeric",
  month: "long",
});

export function Layout() {
  const { pathname } = useLocation();
  const { override } = useClock();
  // Refetched on every navigation and clock change, so the badge stays current.
  const overdue = useAsync(() => api.listOverdue(0), pathname);
  const overdueCount = overdue.data?.total ?? 0;

  const navLinks = (variant: "side" | "tab") =>
    LINKS.map((link) => (
      <NavLink key={link.to} to={link.to} end={link.end} className={`nav-link nav-${variant}`}>
        <Icon name={link.icon} size={variant === "tab" ? 20 : 18} />
        <span>{link.label}</span>
        {link.to === "/overdue" && overdueCount > 0 && (
          <span className="nav-count">{overdueCount}</span>
        )}
      </NavLink>
    ));

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">
            <Icon name="wrench" size={18} />
          </span>
          <span>
            <span className="brand-name">Rental Desk</span>
            <span className="brand-sub">Community tool library</span>
          </span>
        </NavLink>
        <nav className="side-nav" aria-label="Main">
          {navLinks("side")}
        </nav>
        <p className="sidebar-foot">Times shown in IST</p>
      </aside>

      <div className="main">
        <header className="topbar">
          <NavLink to="/" className="brand brand-compact">
            <span className="brand-mark">
              <Icon name="wrench" size={16} />
            </span>
            <span className="brand-name">Rental Desk</span>
          </NavLink>
          <span className="topbar-date">
            <Icon name="calendar" size={16} />
            {istDay.format(override ? new Date(override) : new Date())}
          </span>
          <ClockControl />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>

      <nav className="tab-bar" aria-label="Main">
        {navLinks("tab")}
      </nav>
    </div>
  );
}
