// The Plan screen at Gale: the map (P1-03) with the site config, layer files and replayed
// sol, and the directions to a science target (P1-04) with its three route options. All of
// it comes from the service, or from the demo cache in demo mode.
import type { Conditions } from "@contracts/conditions";
import type { LayerMeta } from "@contracts/layer";
import type { RouteMode } from "@contracts/route_request";
import type { SiteConfig } from "@contracts/site";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { ApiError } from "../api/client";
import { LayersPanel } from "../map/LayersPanel";
import { WalkMap, type MapRoute, type PointsShown } from "../map/WalkMap";
import { Directions, type RouteState } from "./Directions";
import { formatDuration, ROUTE_MODES, routeRequests, type SlopeLimit } from "./routes";
import { Sidebar } from "./Sidebar";

const SITE = "gale";
const ALL_PLANNING: Record<RouteMode, RouteState> = {
  fastest: { status: "loading" },
  science: { status: "loading" },
  cart: { status: "loading" },
};

/** Why the service refused a route: the engine's reason when it gave one. */
function refusal(reason: unknown): string {
  if (reason instanceof ApiError && reason.body && typeof reason.body === "object") {
    const detail = (reason.body as { detail?: unknown }).detail;
    // The screen already says "No safe route:", so drop the engine's own prefix.
    if (typeof detail === "string") return detail.replace(/^no safe route:\s*/i, "");
    // A request that breaks the route_request contract: FastAPI lists what is wrong.
    if (Array.isArray(detail)) {
      return detail.map((item: { msg?: string }) => item.msg ?? JSON.stringify(item)).join("; ");
    }
  }
  return reason instanceof Error ? reason.message : String(reason);
}

interface Loaded {
  site: SiteConfig;
  layers: LayerMeta[];
  conditions: Conditions | null;
}

export function PlanScreen() {
  const { client } = useApi();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [colourLayer, setColourLayer] = useState<string | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [points, setPoints] = useState<PointsShown>({
    targets: true,
    checkpoints: true,
    habitatAndCamp: true,
  });
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
  const [slopeLimit, setSlopeLimit] = useState<SlopeLimit>(20);
  const [chosen, setChosen] = useState<RouteMode>("fastest");
  const [routes, setRoutes] = useState(ALL_PLANNING);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      const [site, layers] = await Promise.all([
        client.site("plan.site", SITE),
        client.layers("plan.layers", SITE),
      ]);
      const conditions =
        site.replayed_sol === null
          ? null
          : await client.conditions("plan.conditions", String(site.replayed_sol));
      if (!cancelled) setLoaded({ site, layers, conditions });
    })().catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const site = loaded?.site ?? null;
  const baseName = site?.files["base_map"]?.split("/").pop();
  const baseLayer = loaded?.layers.find((layer) => layer.name === baseName);
  const colourLayers = loaded?.layers.filter((layer) => layer.name !== baseName) ?? [];
  const selected = site?.science_targets.find((target) => target.id === selectedId);
  // One object per site, so the map doesn't re-fly or rebuild its tiles on every render.
  const origin = useMemo(
    () =>
      site
        ? (site.habitat ?? {
            x: (site.bounds.min_x + site.bounds.max_x) / 2,
            y: (site.bounds.min_y + site.bounds.max_y) / 2,
          })
        : null,
    [site],
  );

  // Plan all three routes for the target, again whenever the slope limit changes.
  useEffect(() => {
    if (!planning || !site || !selected) return;
    let cancelled = false;
    const requests = routeRequests(site, selected, slopeLimit);
    setRoutes(ALL_PLANNING);
    for (const mode of ROUTE_MODES) {
      const request = requests[mode];
      const settle = (state: RouteState) => {
        if (!cancelled) setRoutes((current) => ({ ...current, [mode]: state }));
      };
      if (!request) {
        settle({ status: "none", message: "the site config has no habitat or base camp" });
        continue;
      }
      const step =
        mode === "cart"
          ? `plan.route.cart.${slopeLimit}`
          : `plan.route.${mode}.${selected.id}.${slopeLimit}`;
      client.route(step, request).then(
        (route) => settle({ status: "ok", route }),
        (reason: unknown) => settle({ status: "error", message: refusal(reason) }),
      );
    }
    return () => {
      cancelled = true;
    };
  }, [planning, site, selected, slopeLimit, client]);

  const mapRoutes = useMemo<MapRoute[]>(() => {
    if (!planning) return [];
    return ROUTE_MODES.flatMap((mode) => {
      const state = routes[mode];
      if (state.status !== "ok") return [];
      const { route } = state;
      const isChosen = mode === chosen;
      const extra = mode === "science" && !isChosen ? route.extra_time_vs_fastest_s : null;
      const label = extra === null ? formatDuration(route.total_time_s) : `+${formatDuration(extra)}`;
      return [{ id: `route-${mode}`, path: route.path, label, chosen: isChosen }];
    });
  }, [planning, routes, chosen]);
  const chosenState = routes[chosen];
  const fitTo = useMemo(
    () => (planning && chosenState.status === "ok" ? chosenState.route.path : null),
    [planning, chosenState],
  );

  return (
    <div className="plan">
      {planning && site && selected ? (
        <Directions
          site={site}
          target={selected}
          routes={routes}
          chosen={chosen}
          onChoose={setChosen}
          slopeLimit={slopeLimit}
          onSlopeLimit={setSlopeLimit}
          onBack={() => setPlanning(false)}
        />
      ) : (
        <Sidebar
          site={site}
          conditions={loaded?.conditions ?? null}
          query={query}
          onQuery={setQuery}
          selected={selected}
          onSelect={setSelectedId}
          onDirections={() => setPlanning(true)}
        />
      )}
      {site && origin ? (
        <WalkMap
          site={site}
          origin={origin}
          baseLayer={baseLayer}
          colourLayer={colourLayers.find((layer) => layer.name === colourLayer)}
          points={points}
          selectedTargetId={selectedId}
          onSelectTarget={setSelectedId}
          layersOpen={layersOpen}
          onToggleLayers={() => setLayersOpen((open) => !open)}
          fileUrl={client.fileUrl}
          status={baseLayer ? null : `No base map layer "${baseName}" for ${SITE}.`}
          routes={mapRoutes}
          fitTo={fitTo}
        />
      ) : (
        <div className="map">
          <div className="map__status">
            {error ? `Can't load the map: ${error}` : "Loading the Gale map…"}
          </div>
        </div>
      )}
      {layersOpen && site && (
        <LayersPanel
          baseLayer={baseLayer}
          colourLayers={colourLayers}
          colourLayer={colourLayer}
          onColourLayer={setColourLayer}
          points={points}
          counts={{
            targets: site.science_targets.length,
            checkpoints: site.checkpoints.length,
            habitatAndCamp: Number(Boolean(site.habitat)) + Number(Boolean(site.base_camp)),
          }}
          onPoints={setPoints}
          onClose={() => setLayersOpen(false)}
        />
      )}
    </div>
  );
}
