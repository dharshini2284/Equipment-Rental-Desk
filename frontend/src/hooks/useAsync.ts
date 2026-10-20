import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { useClock } from "./useClock";

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  console.error(error);
  return new ApiError(0, {
    type: "client",
    code: "CLIENT_ERROR",
    message: "Something went wrong in the page. Reload and try again.",
    details: {},
    request_id: null,
  });
}

interface AsyncState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
}

/**
 * Load data and reload it whenever `key` changes, the review clock changes, or `reload()`
 * is called. Earlier data stays visible while a reload is in flight.
 */
export function useAsync<T>(load: () => Promise<T>, key: string) {
  const loadRef = useRef(load);
  loadRef.current = load;
  const { version: clockVersion } = useClock();
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({
    data: undefined,
    error: undefined,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: undefined }));
    loadRef.current().then(
      (data) => {
        if (!cancelled) setState({ data, error: undefined, loading: false });
      },
      (error: unknown) => {
        if (!cancelled)
          setState((previous) => ({ ...previous, error: toApiError(error), loading: false }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, clockVersion, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);
  return { ...state, reload };
}
