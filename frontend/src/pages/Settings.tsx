import { useState } from "react";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { LanguageSwitcher } from "../lib/Language";
import { useLanguage } from "../lib/useLanguage";
import { t } from "../lib/locale";
import type { User } from "../domain";
import { PageHeading, Section } from "../components/ui";
import { NotificationPreferences } from "../components/NotificationPreferences";

export function Settings({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  useLanguage();
  const [verified, setVerified] = useState(Boolean(user.email_verified));
  const [verificationMessage, setVerificationMessage] = useState("");
  const [verificationBusy, setVerificationBusy] = useState(false);
  async function verifyEmail(check = false) {
    setVerificationBusy(true);
    try {
      if (check) {
        const current = await api.me();
        setVerified(Boolean(current.email_verified));
        setVerificationMessage(
          current.email_verified
            ? "Your email is verified."
            : "Your email is not verified yet.",
        );
      } else {
        const response = await api.requestEmailVerification();
        setVerificationMessage(response.message);
      }
    } catch (cause) {
      setVerificationMessage(errorMessage(cause));
    } finally {
      setVerificationBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title={t("Your account & preferences.")}
        description={t(
          "Know how your information is used and what your numbers mean.",
        )}
      />
      <div className="settings-content">
        <Section title={t("Your account")}>
          <dl className="settings-list">
            <div>
              <dt>{t("Name")}</dt>
              <dd>{user.full_name || t("Not supplied")}</dd>
            </div>
            <div>
              <dt>{t("Email")}</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>{t("Currency")}</dt>
              <dd>{t("Bangladeshi taka (BDT)")}</dd>
            </div>
            <div>
              <dt>{t("Financial calendar")}</dt>
              <dd>{t("Asia/Dhaka")}</dd>
            </div>
            <div>
              <dt>{t("Interface")}</dt>
              <dd>
                <LanguageSwitcher />
              </dd>
            </div>
          </dl>
          <p className="muted">
            {t(
              "Profile editing is not available. You can reset your password from the sign-in screen.",
            )}{" "}
          </p>
        </Section>
        <p className="muted">
          {t(
            "Backend explanations and your records remain in their original language.",
          )}
        </p>

        <Section title="Email verification">
          {verified ? (
            <p>Your email address is verified.</p>
          ) : (
            <>
              <p>
                Verify your email before enabling email notifications. After
                following the link, return here and check your status.
              </p>
              <button
                disabled={verificationBusy}
                onClick={() => void verifyEmail()}
              >
                Send verification link
              </button>
              <button
                disabled={verificationBusy}
                onClick={() => void verifyEmail(true)}
              >
                Check verification status
              </button>
            </>
          )}
          {verificationMessage && <p role="status">{verificationMessage}</p>}
        </Section>
        <NotificationPreferences />

        <Section title={t("Data & assumptions")}>
          <p>
            {t(
              "Your recorded net activity is income minus expenses in the selected period. It does not establish your bank or mobile wallet balance.",
            )}{" "}
          </p>
          <p>
            {t(
              "Scheduled records are plans. Marking one paid does not create a transaction. Add the actual transaction separately.",
            )}{" "}
          </p>
          <p>
            {t(
              "Goal savings are amounts you report yourself. Forecasts depend on the completeness of your history and the starting balance you supply.",
            )}{" "}
          </p>
          <p>
            {t(
              "Internal transfers and refunds can affect signed-amount analytics. Review imported categories and records before relying on a comparison.",
            )}{" "}
          </p>
        </Section>
        <Section title={t("Session & privacy")}>
          <p>
            {t(
              "Tokens are held in memory for this tab. Reloading or signing out ends this frontend session. Insight hiding lasts for the current visit.",
            )}{" "}
          </p>
          <p>
            {t(
              "No frontend analytics or external AI calls are enabled. Optional backend provider settings are controlled by the API operator.",
            )}{" "}
          </p>
          <button onClick={onLogout}>{t("Sign out")}</button>
        </Section>
      </div>
    </>
  );
}
