// Empty shell from P1-01 with the live/demo switch from P1-02. The 8 key screens arrive in
// P1-03 to P1-09.
import { ApiProvider, useApi } from "./api/ApiContext";

function ModeSwitch() {
  const { mode, setMode } = useApi();
  return (
    <button type="button" onClick={() => setMode(mode === "live" ? "demo" : "live")}>
      {mode === "live" ? "Live: the service" : "Demo: the cache, offline"}
    </button>
  );
}

export function App() {
  return (
    <ApiProvider>
      <main>
        <h1>RedMark</h1>
        <ModeSwitch />
      </main>
    </ApiProvider>
  );
}
