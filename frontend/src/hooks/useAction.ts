import { useCallback, useState } from "react";
import type { ApiError } from "../api/client";
import { toApiError } from "./useAsync";

/**
 * Run a mutation with a pending flag, so buttons can be disabled while it is in flight
 * (which also stops double-clicks sending two requests), and keep its error or success text.
 */
export function useAction() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | undefined>();
  const [success, setSuccess] = useState<string | undefined>();

  const run = useCallback(
    async <T>(
      action: () => Promise<T>,
      successMessage: (result: T) => string,
    ): Promise<boolean> => {
      setPending(true);
      setError(undefined);
      setSuccess(undefined);
      try {
        const result = await action();
        setSuccess(successMessage(result));
        return true;
      } catch (caught) {
        setError(toApiError(caught));
        return false;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  const clear = useCallback(() => {
    setError(undefined);
    setSuccess(undefined);
  }, []);

  return { run, pending, error, success, clear };
}
