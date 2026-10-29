import { LanguageSwitcher } from "../lib/Language";
import { useLanguage } from "../lib/useLanguage";
import { t } from "../lib/locale";
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";
// Native modal semantics provide focus containment, inert background and Escape.
export function Dialog({
  open,
  title,
  description,
  children,
  onClose,
  busy = false,
  drawer = false,
}: {
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  drawer?: boolean;
}) {
  useLanguage();
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const trigger =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (open && !dialog.open) {
      dialog.showModal();
      dialog
        .querySelector<HTMLElement>("input:not([type=hidden]),textarea,select")
        ?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) dialog.close();
    return () => {
      if (dialog.open) dialog.close();
      if (open && trigger?.isConnected) trigger.focus();
    };
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={drawer ? "dialog drawer" : "dialog"}
      aria-labelledby={id}
      aria-describedby={description ? `${id}-description` : undefined}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
    >
      <header className="dialog-heading">
        <div>
          <h2 id={id}>{title}</h2>
          {description && <p id={`${id}-description`}>{description}</p>}
        </div>
        <LanguageSwitcher />
        <button
          type="button"
          aria-label={t("Close") + " " + title}
          disabled={busy}
          onClick={onClose}
        >
          <X size={19} />
        </button>
      </header>
      <div className="dialog-content" aria-busy={busy}>
        {open ? children : null}
      </div>
    </dialog>
  );
}
