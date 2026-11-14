// The app shell: the Plan screen (map, directions, walk; P1-03 to P1-05) and the Test lab
// (P1-06). The live/demo switch sits in the Plan sidebar footer.
import { useState } from "react";
import { ApiProvider } from "./api/ApiContext";
import { LabScreen } from "./lab/LabScreen";
import { PlanScreen } from "./plan/PlanScreen";

export function App() {
  const [screen, setScreen] = useState<"plan" | "lab">("plan");
  return (
    <ApiProvider>
      {screen === "lab" ? (
        <LabScreen onBack={() => setScreen("plan")} />
      ) : (
        <PlanScreen onOpenLab={() => setScreen("lab")} />
      )}
    </ApiProvider>
  );
}
