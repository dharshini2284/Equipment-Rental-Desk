import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { getClockOverride, setClockOverride } from "../lib/clock";

interface ClockContextValue {
  /** IST ISO string sent as X-Test-Clock, or null for real time. */
  override: string | null;
  setOverride: (value: string | null) => void;
  /** Bumps whenever the clock changes, so pages know to reload. */
  version: number;
}

const ClockContext = createContext<ClockContextValue | null>(null);

export function ClockProvider({ children }: { children: ReactNode }) {
  const [override, setOverrideState] = useState<string | null>(getClockOverride);
  const [version, setVersion] = useState(0);

  const setOverride = useCallback((value: string | null) => {
    setClockOverride(value);
    setOverrideState(value);
    setVersion((v) => v + 1);
  }, []);

  const value = useMemo(
    () => ({ override, setOverride, version }),
    [override, setOverride, version],
  );
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>;
}

export function useClock(): ClockContextValue {
  const context = useContext(ClockContext);
  if (!context) throw new Error("useClock must be used inside <ClockProvider>");
  return context;
}
