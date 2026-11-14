// The Plan screen at Gale (P1-03 map view): the site config, layer files and replayed sol
// from the service, or from the demo cache in demo mode.
import type { Conditions } from "@contracts/conditions";
import type { LayerMeta } from "@contracts/layer";
import type { SiteConfig } from "@contracts/site";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { LayersPanel } from "../map/LayersPanel";
import { WalkMap, type PointsShown } from "../map/WalkMap";
import { Sidebar } from "./Sidebar";

const SITE = "gale";

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

  return (
    <div className="plan">
      <Sidebar
        site={site}
        conditions={loaded?.conditions ?? null}
        query={query}
        onQuery={setQuery}
        selected={selected}
        onSelect={setSelectedId}
      />
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
