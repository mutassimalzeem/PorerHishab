import { LanguageSwitcher } from "../lib/Language";
import { useLanguage } from "../lib/useLanguage";
import { t } from "../lib/locale";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import type { Tokens } from "../domain";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { ErrorNotice, Field } from "../components/ui";
export function Auth({
  onLogin,
  expired,
}: {
  onLogin: (tokens: Tokens) => void;
  expired: boolean;
}) {
  const { language } = useLanguage();
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    document.title =
      (register ? t("Create account") : t("Sign in")) + " | PorerHishab";
  }, [language, register]);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      onLogin(
        register
          ? await api.register(
              String(f.get("email")),
              String(f.get("password")),
              String(f.get("name")),
            )
          : await api.login(String(f.get("email")), String(f.get("password"))),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth">
      <section className="auth-story">
        <a className="brand" href="/">
          <span className="brand-mark">{"\u09aa"}</span>
          <span>
            {t("PorerHishab")}{" "}
            <small lang="bn">
              {"\u09aa\u09b0\u09c7\u09b0 \u09b9\u09bf\u09b8\u09be\u09ac"}
            </small>
          </span>
        </a>
        <div>
          <p className="context">
            {t("A little clarity for what comes next.")}
          </p>
          <h1>
            {t("Today's money.")} <br />
            {t("Tomorrow's plans.")}{" "}
          </h1>
          <p>
            {t(
              "Understand your recorded spending, make room for your commitments, and plan your next move.",
            )}{" "}
          </p>
          <p lang="bn" className="bangla-tagline">
            {
              "\u0986\u099c\u0995\u09c7\u09b0 \u0996\u09b0\u099a, \u0986\u0997\u09be\u09ae\u09c0\u09b0 \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be\u0964"
            }
          </p>
        </div>
        <p className="trust">
          <ShieldCheck size={18} />
          {t("Your records. Clear assumptions. No hidden certainty.")}{" "}
        </p>
      </section>
      <section className="auth-form">
        <div>
          <LanguageSwitcher />
          <span className="context">{t("Welcome to PorerHishab")}</span>
          <h2>
            {register
              ? t("Start with a clearer picture.")
              : t("Pick up where you left off.")}
          </h2>
          <p>
            {register
              ? t(
                  "Create an account, then add your first recorded transaction.",
                )
              : t("Sign in to see your records and upcoming plans.")}
          </p>
          {expired && (
            <p role="status" className="callout">
              {t("Your session ended. Sign in again to continue.")}{" "}
            </p>
          )}
          <form onSubmit={submit}>
            {register && (
              <Field
                label={t("Your name")}
                name="name"
                autoComplete="name"
                maxLength={160}
              />
            )}
            <Field
              label={t("Email address")}
              name="email"
              type="email"
              autoComplete="email"
              required
            />
            <Field
              label={t("Password")}
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={register ? 8 : 1}
              maxLength={72}
            />
            {error && <ErrorNotice message={error} />}
            <button className="button primary" disabled={busy}>
              {busy
                ? t("Please wait...")
                : register
                  ? t("Create account")
                  : t("Sign in")}
              <ArrowUpRight size={18} />
            </button>
          </form>
          <button
            className="text-button auth-switch"
            onClick={() => {
              setRegister(!register);
              setError(null);
            }}
          >
            {register
              ? t("Already have an account? Sign in")
              : t("New here? Create an account")}
          </button>
          <small className="muted">
            {t(
              "Your session stays in memory and ends when you reload this page.",
            )}{" "}
          </small>
        </div>
      </section>
    </main>
  );
}
