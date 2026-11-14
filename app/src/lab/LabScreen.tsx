// The Test lab (P1-06): the judges' screen. A results chart of each measured test's share of
// fixes within 1, 5 and 10 m, overall and by terrain type, next to JPL's benchmark; and the
// tested photos: pick one to see its overlay, its fix and true position on the map, and its
// error. Every number comes from a results file (or the cited benchmark file); a simulated
// result never appears, and a stub shows as pending.
import type { FixResult } from "@contracts/fix_result";
import type { LayerMeta } from "@contracts/layer";
import type { SiteConfig } from "@contracts/site";
import type { TestSummary } from "@contracts/test_summary";
import { useEffect, useMemo, useState } from "react";
import benchmarks from "../../../pitch/benchmarks.json";
import { useApi } from "../api/ApiContext";
import { formatDistance } from "../map/geo";
import { WalkMap } from "../map/WalkMap";
import { latestOnly } from "./latest";
import { chartTests, photoList, type ChartGroup, type ChartTest, type TestedPhoto } from "./results";

const METHODS = ["horizon", "ground", "drone"] as const;
const REFRESH_MS = 15000;
const METHOD_NAMES = { horizon: "Horizon fix", ground: "Ground fix", drone: "Drone fix" } as const;
const SITE_NAMES: Record<string, string> = { gale: "Gale", jezero: "Jezero" };
const benchmark = benchmarks.jpl_drone;

interface SiteMap {
  site: SiteConfig;
  baseLayer: LayerMeta | undefined;
}

const pct = (value: number) => `${Number(value.toFixed(1))}%`;

function Bar({ value, mark }: { value: number; mark?: number | undefined }) {
  return (
    <span className="bar">
      <span className="bar__fill" style={{ width: `${Math.min(100, value)}%` }} />
      {mark !== undefined && <span className="bar__mark" style={{ left: `${mark}%` }} title={`${benchmark.label}: ${pct(mark)}`} />}
      <span className="bar__value">{pct(value)}</span>
    </span>
  );
}

function TestChart({ test }: { test: ChartTest }) {
  const title = `${METHOD_NAMES[test.method]} · ${SITE_NAMES[test.site] ?? test.site}`;
  if (test.status === "pending") {
    return (
      <div className="lab-test">
        <div className="lab-test__head">
          <span className="lab-test__title">{title}</span>
          <span className="chip chip--not-checked">Pending</span>
        </div>
        <p className="empty-note">No measured result yet: {test.test} is still a stub.</p>
      </div>
    );
  }
  const marks = test.method === "drone";
  return (
    <div className="lab-test">
      <div className="lab-test__head">
        <span className="lab-test__title">{title}</span>
        <span className="data">from {test.script}</span>
      </div>
      <div className="lab-grid">
        <span className="label">Terrain</span>
        <span className="label">Median</span>
        <span className="label">Within 1 m</span>
        <span className="label">Within 5 m</span>
        <span className="label">Within 10 m</span>
        {test.groups.map((group: ChartGroup) => (
          <GroupRow key={group.group} group={group} marks={marks} />
        ))}
      </div>
    </div>
  );
}

function GroupRow({ group, marks }: { group: ChartGroup; marks: boolean }) {
  return (
    <>
      <span className="lab-grid__group">
        {group.group} <span className="data">n={group.n}</span>
      </span>
      <span className="data">{formatDistance(group.median_error_m)}</span>
      <Bar value={group.within_1m_pct} />
      <Bar value={group.within_5m_pct} mark={marks ? benchmark.within_5m_pct : undefined} />
      <Bar value={group.within_10m_pct} mark={marks ? benchmark.within_10m_pct : undefined} />
    </>
  );
}

export function LabScreen({ onBack }: { onBack: () => void }) {
  const { client, mode } = useApi();
  const [summaries, setSummaries] = useState<TestSummary[]>([]);
  const [fixes, setFixes] = useState<FixResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [maps, setMaps] = useState<Record<string, SiteMap>>({});

  // Load the results files, and in live mode reload them so the chart follows a new file.
  // Only the newest poll's answer is shown, so a slow older poll can't bring back old numbers.
  useEffect(() => {
    let cancelled = false;
    const show = latestOnly<[TestSummary[], FixResult[]]>(([loadedSummaries, loadedFixes]) => {
      if (cancelled) return;
      setSummaries(loadedSummaries);
      setFixes(loadedFixes);
      setError(null);
    });
    const load = async (): Promise<[TestSummary[], FixResult[]]> => {
      const [loadedSummaries, ...perMethod] = await Promise.all([
        client.summaries("lab.summaries"),
        ...METHODS.map((method) => client.fixes(`lab.fixes.${method}`, method)),
      ]);
      return [loadedSummaries, perMethod.flat()];
    };
    const run = () =>
      show(load()).catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    run();
    const timer = mode === "live" ? setInterval(run, REFRESH_MS) : undefined;
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [client, mode]);

  const tests = useMemo(() => chartTests(summaries), [summaries]);
  const photos = useMemo(() => photoList(fixes), [fixes]);
  const keyOf = (photo: TestedPhoto) => `${photo.method}/${photo.photo_id}`;
  const selected = photos.find((photo) => keyOf(photo) === selectedId) ?? photos[0];

  // The selected photo's site map: its config and base map, loaded once per site. A failed
  // load says so and is tried again on the next refresh, or straight away with Retry.
  const siteId = selected?.site;
  const [siteError, setSiteError] = useState<string | null>(null);
  const [siteAttempt, setSiteAttempt] = useState(0);
  useEffect(() => {
    if (!siteId || maps[siteId]) return;
    let cancelled = false;
    setSiteError(null);
    (async () => {
      const site = await client.site(`lab.site.${siteId}`, siteId);
      const layers = await client.layers(`lab.layers.${siteId}`, siteId).catch(() => [] as LayerMeta[]);
      const baseName = site.files["base_map"]?.split("/").pop();
      if (!cancelled) {
        setMaps((current) => ({
          ...current,
          [siteId]: { site, baseLayer: layers.find((layer) => layer.name === baseName) },
        }));
      }
    })().catch((reason: unknown) => {
      if (!cancelled) setSiteError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => {
      cancelled = true;
    };
  }, [siteId, maps, client, siteAttempt]);
  useEffect(() => {
    if (!siteError) return;
    const timer = setTimeout(() => setSiteAttempt((attempt) => attempt + 1), REFRESH_MS);
    return () => clearTimeout(timer);
  }, [siteError]);

  const siteMap = siteId ? maps[siteId] : undefined;
  const origin = useMemo(() => {
    const site = siteMap?.site;
    if (!site) return null;
    return site.habitat ?? {
      x: (site.bounds.min_x + site.bounds.max_x) / 2,
      y: (site.bounds.min_y + site.bounds.max_y) / 2,
    };
  }, [siteMap]);
  const sharedBy = selected ? photos.filter((photo) => photo.overlay === selected.overlay).length : 0;
  // Frame the pair only when another photo is picked, not on every results reload.
  const selectedKey = selected ? keyOf(selected) : null;
  const fitTo = useMemo(
    () => (selected ? [selected.predicted, selected.truth] : null),
    [selectedKey],
  );

  return (
    <div className="lab">
      <aside className="sidebar lab__side">
        <div className="directions__head">
          <button type="button" className="control" aria-label="Back to planning" onClick={onBack}>
            ‹
          </button>
          <div>
            <div className="directions__crumbs">Measured against the answer key</div>
            <h2 className="directions__title">Test lab</h2>
          </div>
        </div>
        <div className="rule" />
        <div className="sidebar__scroll">
          {error && <p className="route-refused">Can't load the results: {error}</p>}
          <div className="lab-benchmark">
            <span className="lab-test__title">{benchmark.label}</span>
            <span className="data">
              {pct(benchmark.within_5m_pct)} within 5 m · {pct(benchmark.within_10m_pct)} within 10 m ·{" "}
              <a href={benchmark.source.url} target="_blank" rel="noreferrer">
                {benchmark.source.title}
              </a>
            </span>
          </div>
          {tests.map((test) => (
            <TestChart key={test.test} test={test} />
          ))}

          <div className="section-head">
            <span className="label">Tested photos · {photos.length}</span>
            <span className="label">Error</span>
          </div>
          {photos.map((photo) => (
            <PhotoRow
              key={keyOf(photo)}
              photo={photo}
              on={selected !== undefined && keyOf(photo) === keyOf(selected)}
              onClick={() => setSelectedId(keyOf(photo))}
            />
          ))}
        </div>
      </aside>

      <section className="lab__detail">
        {selected ? (
          <>
            <div className="lab__photo">
              <figure className="lab__figure">
                <a href={client.fileUrl(`/overlays/${selected.overlay}`)} target="_blank" rel="noreferrer" title="Open the overlay full size">
                  <img src={client.fileUrl(`/overlays/${selected.overlay}`)} alt={`Overlay for ${selected.photo_id}`} />
                </a>
                <figcaption className="data">
                  {sharedBy > 1
                    ? `Overlay for this rover stop, shared by ${sharedBy} tested photos; it may not show this frame. The results carry no per-photo image yet.`
                    : "Overlay for this photo."}
                </figcaption>
              </figure>
              <div className="lab__errors">
                <span className="label">{METHOD_NAMES[selected.method]} · {selected.photo_id}</span>
                <div className="place__stats">
                  <div className="place__stat">
                    <span className="label">Position error</span>
                    <span className="lab__readout">{formatDistance(selected.position_error_m)}</span>
                  </div>
                  {selected.heading_error_deg !== null && (
                    <div className="place__stat">
                      <span className="label">Heading error</span>
                      <span className="lab__readout">{Number(selected.heading_error_deg.toFixed(1))}°</span>
                    </div>
                  )}
                  <div className="place__stat">
                    <span className="label">Terrain</span>
                    <span className="lab__readout lab__readout--small">{selected.terrain_type}</span>
                  </div>
                </div>
              </div>
            </div>
            {siteMap && origin ? (
              <WalkMap
                site={siteMap.site}
                origin={origin}
                baseLayer={siteMap.baseLayer}
                colourLayer={undefined}
                points={{ targets: false, checkpoints: false, habitatAndCamp: true }}
                selectedTargetId={null}
                onSelectTarget={() => {}}
                layersOpen={false}
                onToggleLayers={() => {}}
                fileUrl={client.fileUrl}
                status={null}
                routes={[]}
                fitTo={fitTo}
                pair={{
                  predicted: selected.predicted,
                  truth: selected.truth,
                  label: formatDistance(selected.position_error_m),
                }}
              />
            ) : (
              <div className="map">
                <div className="map__status">
                  {siteError ? (
                    <>
                      Can't load the {SITE_NAMES[selected.site] ?? selected.site} map: {siteError}{" "}
                      <button type="button" className="sidebar__nav" onClick={() => setSiteAttempt((attempt) => attempt + 1)}>
                        Retry
                      </button>
                    </>
                  ) : (
                    `Loading the ${SITE_NAMES[selected.site] ?? selected.site} map…`
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="map">
            <div className="map__status">No tested photos with measured results yet.</div>
          </div>
        )}
      </section>
    </div>
  );
}

function PhotoRow({ photo, on, onClick }: { photo: TestedPhoto; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`target-row${on ? " target-row--on" : ""}`} onClick={onClick}>
      <span className="lab-method">{photo.method[0]!.toUpperCase()}</span>
      <span className="target-row__text">
        <span className="target-row__name lab-photo-id">{photo.photo_id}</span>
        <span className="data">
          {SITE_NAMES[photo.site] ?? photo.site} · {photo.terrain_type}
        </span>
      </span>
      <span className="data lab-error">{formatDistance(photo.position_error_m)}</span>
    </button>
  );
}
