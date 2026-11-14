// The Drone fix screen (P1-09): the drone's top-down photo with the detected astronauts, the
// photo's matched outline on the Gale map, and the fix itself. The Gale drone fix is
// simulated (the photo is cut from the map it is matched to), so the screen says so even
// when it falls back to the static images, and reports no numbers from it (team plan).
import type { FixResult } from "@contracts/fix_result";
import { useEffect, useState } from "react";
import { useApi } from "../api/ApiContext";
import { FixCard } from "../ui/FixCard";
import { Panel } from "../ui/Panel";
import { WithFallback } from "../ui/WithFallback";
import { bundledDroneImages, DRONE_FIX_FALLBACK, droneFixImages, loadDroneFix } from "./droneFix";

type Loaded = { status: "loading" } | { status: "ok"; fix: FixResult } | { status: "error"; message: string };

export function DroneFixScreen({ onClose }: { onClose: () => void }) {
  const { client } = useApi();
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadDroneFix(client).then(
      (fix) => !cancelled && setLoaded({ status: "ok", fix }),
      (reason: unknown) =>
        !cancelled && setLoaded({ status: "error", message: reason instanceof Error ? reason.message : String(reason) }),
    );
    return () => {
      cancelled = true;
    };
  }, [client]);

  const images =
    loaded.status === "ok"
      ? droneFixImages(loaded.fix, client.mode, { bundled: bundledDroneImages, fileUrl: client.fileUrl })
      : DRONE_FIX_FALLBACK;

  return (
    <Panel title="Drone fix" label={<span className="chip chip--simulated">Simulated at Gale</span>} onClose={onClose}>
      <p className="panel__note">
        The drone's photo is cut from the same Gale map it is matched to, so it shows the pipeline,
        not accuracy. Astronaut detection is a mock-up.
      </p>
      {loaded.status === "error" && (
        <p className="panel__note panel__note--warn">
          Can't load the drone fix ({loaded.message}); showing the saved images.
        </p>
      )}
      <div className="drone-fix">
        <figure className="drone-fix__figure">
          <WithFallback src={images.photo} fallback={DRONE_FIX_FALLBACK.photo} alt="The drone's top-down photo with the detected astronauts circled" />
          <figcaption className="data">Top-down photo · detected astronauts in yellow</figcaption>
        </figure>
        <figure className="drone-fix__figure drone-fix__figure--wide">
          <WithFallback src={images.sheet} fallback={DRONE_FIX_FALLBACK.sheet} alt="The photo's matched outline on the Gale map, with the astronauts and the crew's fix" />
          <figcaption className="data">
            Matched outline on the map (red) · astronauts (orange) · crew's fix (green)
          </figcaption>
        </figure>
      </div>
      {loaded.status === "ok" && (
        <FixCard method={loaded.fix.method} simulated={loaded.fix.simulated} source={`Drone photo · ${loaded.fix.photo_id}`}>
          <p className="panel__note">No numbers are reported from the simulated Gale drone fix.</p>
        </FixCard>
      )}
    </Panel>
  );
}
