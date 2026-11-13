import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";

export function AccountRecovery({
  mode,
}: {
  mode: "verify-email" | "reset-password" | "forgot-password";
}) {
  const [token, setToken] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("token") || "",
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    // Keep challenge values out of browser history, HTTP URLs and referrers.
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    document.title = "Account recovery | PorerHishab";
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const response =
        mode === "forgot-password"
          ? await api.requestPasswordReset(String(fields.get("email")))
          : mode === "verify-email"
            ? await api.confirmEmailVerification(token)
            : await api.confirmPasswordReset(
                token,
                String(fields.get("password")),
              );
      setMessage(response.message);
      setDone(true);
      setToken("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  const title =
    mode === "verify-email" ? "Verify your email" : "Reset your password";
  return (
    <main className="auth">
      <section className="auth-form">
        <h1>{title}</h1>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {!done && (
          <form onSubmit={(event) => void submit(event)}>
            {mode === "forgot-password" ? (
              <label>
                Email
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                />
              </label>
            ) : !token ? (
              <p>
                This link is missing its verification code. Request a new link.
              </p>
            ) : mode === "reset-password" ? (
              <label>
                New password
                <input
                  name="password"
                  type="password"
                  minLength={8}
                  autoComplete="new-password"
                  required
                />
                <small>Use at least 8 characters.</small>
              </label>
            ) : (
              <p>Confirm that this is your email address.</p>
            )}
            <button disabled={busy || (mode !== "forgot-password" && !token)}>
              {busy
                ? "Please wait..."
                : mode === "forgot-password"
                  ? "Send recovery link"
                  : "Confirm"}
            </button>
          </form>
        )}
        <a href="/">Return to sign in</a>
      </section>
    </main>
  );
}
