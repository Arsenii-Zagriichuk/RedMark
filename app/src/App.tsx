// The app shell. P1-03 brings the Plan screen's map; the other key screens arrive in P1-04
// to P1-09. The live/demo switch sits in the sidebar footer.
import { ApiProvider } from "./api/ApiContext";
import { PlanScreen } from "./plan/PlanScreen";

export function App() {
  return (
    <ApiProvider>
      <PlanScreen />
    </ApiProvider>
  );
}
