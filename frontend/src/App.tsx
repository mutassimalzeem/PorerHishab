import { LanguageSwitcher } from "./lib/Language";
import { useLanguage } from "./lib/useLanguage";
import { t, uiLabel } from "./lib/locale";
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
  const { language } = useLanguage();
  const [open, setOpen] = useState(false);
  const mobile = useMediaQuery("(max-width:760px)");
  const location = useLocation();
  useEffect(() => {
    document.title = `${uiLabel(navigation.find((n) => n.to === location.pathname)?.label || t("Settings"))} | PorerHishab`;
  }, [location.pathname, language]);
  useEffect(() => {
    document.getElementById("main")?.focus();
  }, [location.pathname]);
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        {t("Skip to content")}{" "}
      </a>
      {mobile ? (
        <Dialog
          open={open}
          title={t("Your workspace")}
          drawer
          onClose={() => setOpen(false)}
        >
          <div className="mobile-nav-content">
            {" "}
            <Link to="/" className="brand" onClick={() => setOpen(false)}>
              <span className="brand-mark">{"\u09aa"}</span>
              <span>
                {t("PorerHishab")}{" "}
                <small lang="bn">
                  {"\u09aa\u09b0\u09c7\u09b0 \u09b9\u09bf\u09b8\u09be\u09ac"}
                </small>
              </span>
            </Link>
            <nav aria-label={t("Main navigation")}>
              {navigation.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to === "/"}
                  onClick={() => setOpen(false)}
                >
                  <n.icon size={19} strokeWidth={1.7} />
                  {uiLabel(n.label)}
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
                  {t("A little ahead.")} <br />
                  {t("A lot more clear.")}{" "}
                </p>
              </div>
              <NavLink to="/settings" onClick={() => setOpen(false)}>
                <SettingsIcon size={18} />
                {t("Settings")}{" "}
              </NavLink>
              <button className="text-button" onClick={onLogout}>
                <LogOut size={17} />
                {t("Sign out")}{" "}
              </button>
              <div className="account">
                <span className="avatar">
                  {(user.full_name || user.email).slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <strong>{user.full_name || t("Your account")}</strong>
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
              {t("PorerHishab")}{" "}
              <small lang="bn">
                {"\u09aa\u09b0\u09c7\u09b0 \u09b9\u09bf\u09b8\u09be\u09ac"}
              </small>
            </span>
          </Link>
          <nav aria-label={t("Main navigation")}>
            {navigation.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                onClick={() => setOpen(false)}
              >
                <n.icon size={19} strokeWidth={1.7} />
                {uiLabel(n.label)}
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
                {t("A little ahead.")} <br />
                {t("A lot more clear.")}{" "}
              </p>
            </div>
            <NavLink to="/settings" onClick={() => setOpen(false)}>
              <SettingsIcon size={18} />
              {t("Settings")}{" "}
            </NavLink>
            <button className="text-button" onClick={onLogout}>
              <LogOut size={17} />
              {t("Sign out")}{" "}
            </button>
            <div className="account">
              <span className="avatar">
                {(user.full_name || user.email).slice(0, 1).toUpperCase()}
              </span>
              <div>
                <strong>{user.full_name || t("Your account")}</strong>
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
            aria-label={t("Open navigation")}
            aria-expanded={open}
            onClick={() => setOpen(true)}
          >
            <Menu size={21} />
          </button>
          <span className="workspace-label">
            {t("Personal workspace")} <span aria-hidden="true">/</span>{" "}
            <strong>
              {uiLabel(
                navigation.find((n) => n.to === location.pathname)?.label ||
                  t("Settings"),
              )}
            </strong>
          </span>
          <time dateTime={today()}>{date(today())}</time>
          <LanguageSwitcher />
          <span className="currency-label">{t("BDT")}</span>
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
                  title={t("This page is not here")}
                  action={
                    <Link to="/" className="button">
                      {t("Back to overview")}{" "}
                    </Link>
                  }
                >
                  {t(
                    "Your financial records are available from the main navigation.",
                  )}{" "}
                </Empty>
              }
            />
          </Routes>
          <footer className="footer">
            <span>{t("PorerHishab")}</span>
            <span>
              {t("Based on your records. Built for what comes next.")}
            </span>
          </footer>
        </main>
      </div>
      {mobile && (
        <nav className="mobile-quick-nav" aria-label={t("Quick navigation")}>
          {navigation
            .filter((n) =>
              ["/", "/cashflow", "/transactions", "/ask"].includes(n.to),
            )
            .map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                <n.icon size={20} />
                <span>{n.to === "/ask" ? t("Ask") : uiLabel(n.label)}</span>
              </NavLink>
            ))}
        </nav>
      )}
    </div>
  );
}
export default function App() {
  useLanguage();
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
              {t("Opening your workspace...")}{" "}
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
