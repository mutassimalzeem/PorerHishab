import { useEffect, useState, useCallback } from "react";
import { errorMessage } from "./format";
export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}
export function useResource<T>(
  loader: () => Promise<T>,
  refreshKey: string | number | null = 0,
): Resource<T> {
  const [state, setState] = useState<{
    data: T | null;
    loading: boolean;
    error: string | null;
  }>({ data: null, loading: true, error: null });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ data: null, loading: true, error: null });
    });
    loader()
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (active)
          setState({ data: null, loading: false, error: errorMessage(error) });
      });
    return () => {
      active = false;
    };
  }, [loader, revision, refreshKey]);
  return { ...state, retry: useCallback(() => setRevision((v) => v + 1), []) };
}
