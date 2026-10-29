import { useSyncExternalStore } from "react";
import { getLanguage, setLanguage, subscribeLanguage, t } from "./locale";
export function useLanguage() {
  const language = useSyncExternalStore(
    subscribeLanguage,
    getLanguage,
    () => "en" as const,
  );
  return { language, setLanguage, t };
}
