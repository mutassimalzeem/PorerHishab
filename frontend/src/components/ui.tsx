import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel, digits, errorText } from "../lib/locale";
import { useId } from "react";
import type { ReactNode, InputHTMLAttributes } from "react";
import { AlertCircle, ArrowUpRight, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import type { Resource } from "../lib/useResource";
import { money } from "../lib/format";
import type { Money } from "../domain";
export function Amount({
  value,
  className = "",
}: {
  value: Money | number | null | undefined;
  className?: string;
}) {
  useLanguage();
  return <span className={`amount ${className}`}>{money(value)}</span>;
}
export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  useLanguage();
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        {...props}
        aria-describedby={hint ? `${id}-hint` : undefined}
      />
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </label>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  useLanguage();
  return (
    <div className="empty">
      <Inbox size={26} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  useLanguage();
  return (
    <div className="error" role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <span>{errorText(message)}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          {t("Try again")}{" "}
        </button>
      )}
    </div>
  );
}
export function Loading({
  label = t("Loading your records..."),
}: {
  label?: string;
}) {
  useLanguage();
  return (
    <div className="loading" role="status">
      <p>{label}</p>
      <div className="loading-record" aria-hidden="true">
        <i />
        <div>
          <span />
          <span />
        </div>
        <b />
      </div>
      <div className="loading-record" aria-hidden="true">
        <i />
        <div>
          <span />
          <span />
        </div>
        <b />
      </div>
      <div className="loading-record" aria-hidden="true">
        <i />
        <div>
          <span />
          <span />
        </div>
        <b />
      </div>
    </div>
  );
}
export function ResourceView<T>({
  resource,
  children,
  label,
}: {
  resource: Resource<T>;
  children: (data: T) => ReactNode;
  label?: string;
}) {
  useLanguage();
  if (resource.loading) return <Loading label={label} />;
  if (resource.error)
    return <ErrorNotice message={resource.error} retry={resource.retry} />;
  return resource.data !== null ? children(resource.data) : null;
}
export function Notes({
  assumptions = [],
  limitations = [],
}: {
  assumptions?: string[];
  limitations?: string[];
}) {
  useLanguage();
  if (!assumptions.length && !limitations.length) return null;
  return (
    <details className="notes">
      <summary>{t("Assumptions & data limitations")}</summary>
      {assumptions.length > 0 && (
        <>
          <h4>{t("Assumptions")}</h4>
          <ul>
            {assumptions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </>
      )}
      {limitations.length > 0 && (
        <>
          <h4>{t("Limitations")}</h4>
          <ul>
            {limitations.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </>
      )}
    </details>
  );
}
export function Section({
  title,
  children,
  link,
  to,
}: {
  title: string;
  children: ReactNode;
  link?: string;
  to?: string;
}) {
  useLanguage();
  return (
    <section className="section">
      <div className="section-heading">
        <h2>{title}</h2>
        {link && to && (
          <Link to={to}>
            {link}
            <ArrowUpRight size={16} aria-hidden="true" />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}
export function PageHeading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  useLanguage();
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}
function EvidenceValue({
  value,
  field = "",
}: {
  value: unknown;
  field?: string;
}) {
  useLanguage();
  if (value === null || value === undefined)
    return <span className="muted">{t("Not available")}</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ol className="evidence-list">
        {value.map((v, i) => (
          <li key={i}>
            <EvidenceValue value={v} />
          </li>
        ))}
      </ol>
    ) : (
      <span className="muted">{t("No records supplied")}</span>
    );
  if (typeof value === "object")
    return (
      <dl className="evidence-grid">
        {Object.entries(value).map(([key, v]) => (
          <div key={key}>
            <dt>{uiLabel(key.replaceAll("_", " "))}</dt>
            <dd>
              <EvidenceValue value={v} field={key} />
            </dd>
          </div>
        ))}
      </dl>
    );
  if (typeof value === "boolean")
    return <span>{value ? t("Yes") : t("No")}</span>;
  if (
    (typeof value === "string" || typeof value === "number") &&
    /amount|income|expenses|balance|saving|net$|reserve|capacity|delta$/.test(
      field,
    ) &&
    !field.includes("count") &&
    Number.isFinite(Number(value))
  )
    return <Amount value={value} />;
  if (typeof value === "number") return <span>{digits(value)}</span>;
  return <span>{String(value)}</span>;
}
export function Evidence({
  value,
  label = t("View evidence"),
}: {
  value: unknown;
  label?: string;
}) {
  useLanguage();
  return (
    <details className="notes">
      <summary>{label}</summary>
      <EvidenceValue value={value} />
    </details>
  );
}
export function Pager({
  offset,
  total,
  limit,
  onChange,
}: {
  offset: number;
  total: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  useLanguage();
  return (
    <div className="pager">
      <span>
        {total
          ? digits(offset + 1) +
            " - " +
            digits(Math.min(offset + limit, total)) +
            " " +
            t("of") +
            " " +
            digits(total)
          : t("0 records")}
      </span>
      <button
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        {t("Previous")}{" "}
      </button>
      <button
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        {t("Next")}{" "}
      </button>
    </div>
  );
}
