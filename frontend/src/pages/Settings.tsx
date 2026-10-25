import type { User } from "../domain";
import { PageHeading, Section } from "../components/ui";
export function Settings({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  return (
    <>
      <PageHeading
        title="Your account & preferences."
        description="Know how your information is used and what your numbers mean."
      />
      <div className="settings-content">
        <Section title="Your account">
          <dl className="settings-list">
            <div>
              <dt>Name</dt>
              <dd>{user.full_name || "Not supplied"}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Currency</dt>
              <dd>Bangladeshi taka (BDT)</dd>
            </div>
            <div>
              <dt>Financial calendar</dt>
              <dd>Asia/Dhaka</dd>
            </div>
            <div>
              <dt>Interface</dt>
              <dd>English, with Bangla-ready content and Latin numerals</dd>
            </div>
          </dl>
          <p className="muted">
            Profile editing and password reset are not available through the
            current API.
          </p>
        </Section>
        <Section title="Data & assumptions">
          <p>
            Your recorded net activity is income minus expenses in the selected
            period. It does not establish your bank or mobile wallet balance.
          </p>
          <p>
            Scheduled records are plans. Marking one paid does not create a
            transaction. Add the actual transaction separately.
          </p>
          <p>
            Goal savings are amounts you report yourself. Forecasts depend on
            the completeness of your history and the starting balance you
            supply.
          </p>
          <p>
            Internal transfers and refunds can affect signed-amount analytics.
            Review imported categories and records before relying on a
            comparison.
          </p>
        </Section>
        <Section title="Session & privacy">
          <p>
            Tokens are held in memory for this tab. Reloading or signing out
            ends this frontend session. Insight hiding lasts for the current
            visit.
          </p>
          <p>
            No frontend analytics or external AI calls are enabled. Optional
            backend provider settings are controlled by the API operator.
          </p>
          <button onClick={onLogout}>Sign out</button>
        </Section>
      </div>
    </>
  );
}
