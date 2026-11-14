// The live/demo switch: every screen gets its client from useApi(), so one toggle moves
// the whole app between the service and the demo cache. The choice survives a reload.
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { createClient, type ApiClient, type Mode } from "./client";
import { demoCache } from "./demoCache";

const SERVICE_URL: string = import.meta.env.VITE_SERVICE_URL ?? "http://127.0.0.1:8000";
const MODE_KEY = "redmark.mode";

interface Api {
  client: ApiClient;
  mode: Mode;
  setMode: (mode: Mode) => void;
}

const ApiContext = createContext<Api | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(() =>
    localStorage.getItem(MODE_KEY) === "demo" ? "demo" : "live",
  );
  const api = useMemo<Api>(
    () => ({
      client: createClient({ mode, baseUrl: SERVICE_URL, cache: demoCache }),
      mode,
      setMode: (next) => {
        localStorage.setItem(MODE_KEY, next);
        setModeState(next);
      },
    }),
    [mode],
  );
  return <ApiContext value={api}>{children}</ApiContext>;
}

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi() needs an <ApiProvider> above it");
  return api;
}
