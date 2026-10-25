import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  ArrowUpRight,
  ChartNoAxesCombined,
  ChartNoAxesColumn,
  House,
  List,
  LogOut,
  Menu,
  MessageSquare,
  Settings as SettingsIcon,
  Target,
} from "lucide-react";
import { Dialog } from "./components/Dialog";
import { useMediaQuery } from "./lib/useMediaQuery";
import type { Tokens, User } from "./domain";
import { api, setSession } from "./lib/api";
import { date, errorMessage, today } from "./lib/format";
import { Auth } from "./pages/Auth";
import { Dashboard } from "./pages/Dashboard";
import { Cashflow } from "./pages/Cashflow";
import { Transactions } from "./pages/Transactions";
import { Plans } from "./pages/Plans";
import { Insights } from "./pages/Insights";
import { Ask } from "./pages/Ask";
import { Settings } from "./pages/Settings";
import { Empty, ErrorNotice } from "./components/ui";
const navigation = [
  { to: "/", label: "Overview", icon: House },
  { to: "/cashflow", label: "Cashflow", icon: ChartNoAxesCombined },
  { to: "/transactions", label: "Transactions", icon: List },
  { to: "/plans", label: "Plans", icon: Target },
  { to: "/insights", label: "Insights", icon: ChartNoAxesColumn },
  { to: "/ask", label: "Ask PorerHishab", icon: MessageSquare },
];
function Shell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const mobile = useMediaQuery("(max-width:760px)");
  const location = useLocation();
  useEffect(() => {
    document.title = `${navigation.find((n) => n.to === location.pathname)?.label || "Settings"} | PorerHishab`;
    document.getElementById("main")?.focus();
  }, [location.pathname]);
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      {mobile ? (
        <Dialog
          open={open}
          title="Your workspace"
          drawer
          onClose={() => setOpen(false)}
        >
          <div className="mobile-nav-content">
            {" "}
            <Link to="/" className="brand" onClick={() => setOpen(false)}>
              <span className="brand-mark">{"\u09aa"}</span>
              <span>
                PorerHishab
                <small lang="bn">
                  {"\u09aa\u09b0\u09c7\u09b0 \u09b9\u09bf\u09b8\u09be\u09ac"}
                </small>
              </span>
            </Link>
            <nav aria-label="Main navigation">
              {navigation.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to === "/"}
                  onClick={() => setOpen(false)}
                >
                  <n.icon size={19} strokeWidth={1.7} />
                  {n.label}
                  {n.to === "/ask" && (
                    <ArrowUpRight size={14} className="nav-arrow" />
                  )}
                </NavLink>
              ))}
            </nav>
            <div className="sidebar-bottom">
              <div className="sidebar-note">
                <span className="small-mark" />
                <p>
                  A little ahead.
                  <br />A lot more clear.
                </p>
              </div>
              <NavLink to="/settings" onClick={() => setOpen(false)}>
                <SettingsIcon size={18} />
                Settings
              </NavLink>
              <button className="text-button" onClick={onLogout}>
                <LogOut size={17} />
                Sign out
              </button>
              <div className="account">
                <span className="avatar">
                  {(user.full_name || user.email).slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <strong>{user.full_name || "Your account"}</strong>
                  <small>{user.email}</small>
                </div>
              </div>
            </div>
          </div>
        </Dialog>
      ) : (
        <aside className="sidebar">
          {" "}
          <Link to="/" className="brand" onClick={() => setOpen(false)}>
            <span className="brand-mark">{"\u09aa"}</span>
            <span>
              PorerHishab
              <small lang="bn">
                {"\u09aa\u09b0\u09c7\u09b0 \u09b9\u09bf\u09b8\u09be\u09ac"}
              </small>
            </span>
          </Link>
          <nav aria-label="Main navigation">
            {navigation.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                onClick={() => setOpen(false)}
              >
                <n.icon size={19} strokeWidth={1.7} />
                {n.label}
                {n.to === "/ask" && (
                  <ArrowUpRight size={14} className="nav-arrow" />
                )}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-note">
              <span className="small-mark" />
              <p>
                A little ahead.
                <br />A lot more clear.
              </p>
            </div>
            <NavLink to="/settings" onClick={() => setOpen(false)}>
              <SettingsIcon size={18} />
              Settings
            </NavLink>
            <button className="text-button" onClick={onLogout}>
              <LogOut size={17} />
              Sign out
            </button>
            <div className="account">
              <span className="avatar">
                {(user.full_name || user.email).slice(0, 1).toUpperCase()}
              </span>
              <div>
                <strong>{user.full_name || "Your account"}</strong>
                <small>{user.email}</small>
              </div>
            </div>
          </div>
        </aside>
      )}
      <div className="workspace">
        <header className="topbar">
          <button
            id="nav-toggle"
            className="mobile-menu"
            aria-label="Open navigation"
            aria-expanded={open}
            onClick={() => setOpen(true)}
          >
            <Menu size={21} />
          </button>
          <span className="workspace-label">
            Personal workspace <span aria-hidden="true">/</span>{" "}
            <strong>
              {navigation.find((n) => n.to === location.pathname)?.label ||
                "Settings"}
            </strong>
          </span>
          <time dateTime={today()}>{date(today())}</time>
          <span className="currency-label">BDT</span>
        </header>
        <main id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/cashflow" element={<Cashflow />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/plans" element={<Plans />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/ask" element={<Ask />} />
            <Route
              path="/settings"
              element={<Settings user={user} onLogout={onLogout} />}
            />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route
              path="*"
              element={
                <Empty
                  title="This page is not here"
                  action={
                    <Link to="/" className="button">
                      Back to overview
                    </Link>
                  }
                >
                  Your financial records are available from the main navigation.
                </Empty>
              }
            />
          </Routes>
          <footer className="footer">
            <span>PorerHishab</span>
            <span>Based on your records. Built for what comes next.</span>
          </footer>
        </main>
      </div>
      {mobile && (
        <nav className="mobile-quick-nav" aria-label="Quick navigation">
          {navigation
            .filter((n) =>
              ["/", "/cashflow", "/transactions", "/ask"].includes(n.to),
            )
            .map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                <n.icon size={20} />
                <span>{n.to === "/ask" ? "Ask" : n.label}</span>
              </NavLink>
            ))}
        </nav>
      )}
    </div>
  );
}
export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    function expire() {
      setUser(null);
      setExpired(true);
    }
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);
  async function login(tokens: Tokens) {
    setSession(tokens);
    setLoading(true);
    setError(null);
    try {
      setUser(await api.me());
      setExpired(false);
    } catch (e) {
      setSession(null);
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  function logout() {
    setSession(null);
    setUser(null);
    setError(null);
  }
  return (
    <BrowserRouter>
      {user ? (
        <Shell user={user} onLogout={logout} />
      ) : (
        <>
          {error && <ErrorNotice message={error} />}{" "}
          {loading ? (
            <div className="auth-pending" role="status">
              Opening your workspace...
            </div>
          ) : (
            <Auth
              onLogin={(tokens) => {
                void login(tokens);
              }}
              expired={expired}
            />
          )}
        </>
      )}
    </BrowserRouter>
  );
}
