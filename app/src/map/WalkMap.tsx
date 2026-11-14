// The Gale map (P1-03): deck.gl in local metres, the base photo map and one colour layer as
// tiles, the habitat, base camp, science targets and checkpoints from the site config, the
// 2 km walk limit, and pan, zoom, north-up and 3D tilt. Draping on 3D terrain waits for an
// elevation layer from Person 2.
import { FlyToInterpolator, MapView, WebMercatorViewport, type MapViewState } from "@deck.gl/core";
import { BitmapLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";
import type { LayerMeta } from "@contracts/layer";
import type { Point, SiteConfig } from "@contracts/site";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  FlagIcon,
  HouseIcon,
  LayersIcon,
  MinusIcon,
  NorthIcon,
  PlusIcon,
} from "../ui/icons";
import {
  formatResolution,
  fromLngLat,
  metresPerPixel,
  tileZoomFor,
  tilesIn,
  toLngLat,
  WALK_LIMIT_M,
  zoomToFit,
  type LngLat,
} from "./geo";

/** A planned route drawn on the map, with its label at the middle of the path. */
export interface MapRoute {
  id: string;
  path: Point[];
  label: string;
  chosen: boolean;
}

/** The crew during a walk: the estimated position and its uncertainty circle. */
export interface CrewPosition {
  position: Point;
  uncertainty_m: number;
  level: "sure" | "check" | "over";
  chip: string;
  /** Direction of travel from map north; the followed view turns to it. */
  heading: number;
}

export interface PointsShown {
  targets: boolean;
  checkpoints: boolean;
  habitatAndCamp: boolean;
}

interface Props {
  site: SiteConfig;
  origin: Point;
  baseLayer: LayerMeta | undefined;
  colourLayer: LayerMeta | undefined;
  points: PointsShown;
  selectedTargetId: string | null;
  onSelectTarget: (id: string) => void;
  layersOpen: boolean;
  onToggleLayers: () => void;
  fileUrl: (path: string) => string;
  status: string | null;
  routes: MapRoute[];
  /** Points the view frames when they change, such as the chosen route. */
  fitTo: Point[] | null;
  /** In the Test lab: a fix's estimated position and the answer key's true position. */
  pair?: { predicted: Point; truth: Point; label: string } | null;
  /** During a walk: the view follows the crew until the user pans away. */
  crew?: CrewPosition | null;
}

const MAP_VIEW = new MapView({ id: "map", repeat: false });
const TILT_DEGREES = 50;
const MAX_DETAIL_TILES = 150;
const COLOUR_OPACITY = 0.85;
const SCALE_STEPS_M = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
const SCALE_TARGET_PX = 100;
const FIT_PADDING = 1.4;
const ROUTE_COLOUR: [number, number, number] = [111, 155, 255];
const ALTERNATIVE_COLOUR: [number, number, number, number] = [154, 166, 191, 210];
const OUTLINE_COLOUR: [number, number, number, number] = [5, 7, 13, 200];
const FOLLOW_ZOOM = 17.5;
const FOLLOW_PITCH = 45;
const LEVEL_COLOURS: Record<CrewPosition["level"], [number, number, number]> = {
  sure: [61, 220, 151],
  check: [255, 176, 32],
  over: [252, 61, 33],
};

/** The map's size: first from the page, then from deck.gl, so markers and tiles agree. */
function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size, setSize] as const;
}

function rasterLayers(
  layer: LayerMeta,
  site: SiteConfig,
  viewport: WebMercatorViewport,
  origin: Point,
  fileUrl: (path: string) => string,
  opacity: number,
) {
  const url = (path: string) => fileUrl(`/layers/${site.site}/${layer.name}/${path}`);
  const [minLng, minLat, maxLng, maxLat] = viewport.getBounds();
  const southWest = fromLngLat([minLng, minLat], origin);
  const northEast = fromLngLat([maxLng, maxLat], origin);
  const view = { west: southWest.x, south: southWest.y, east: northEast.x, north: northEast.y };
  const whole = {
    west: layer.bounds.min_x,
    south: layer.bounds.min_y,
    east: layer.bounds.max_x,
    north: layer.bounds.max_y,
  };
  const overview = tilesIn(layer, layer.tiles.min_zoom, whole, url);
  const screen = metresPerPixel(viewport.zoom) / window.devicePixelRatio;
  let zoom = tileZoomFor(layer, screen);
  let detail = zoom > layer.tiles.min_zoom ? tilesIn(layer, zoom, view, url) : [];
  while (detail.length > MAX_DETAIL_TILES && zoom > layer.tiles.min_zoom) {
    zoom -= 1;
    detail = tilesIn(layer, zoom, view, url);
  }
  return [...overview, ...detail].map((tile) => {
    const [west, south, east, north] = tile.bounds;
    const [w, s] = toLngLat({ x: west, y: south }, origin);
    const [e, n] = toLngLat({ x: east, y: north }, origin);
    return new BitmapLayer({
      id: tile.key,
      image: tile.url,
      bounds: [w, s, e, n],
      opacity,
      textureParameters: { minFilter: "linear", magFilter: "linear" },
    });
  });
}

function ScaleBar({ zoom }: { zoom: number }) {
  const mpp = metresPerPixel(zoom);
  const metres = SCALE_STEPS_M.reduce((best, step) =>
    Math.abs(step / mpp - SCALE_TARGET_PX) < Math.abs(best / mpp - SCALE_TARGET_PX) ? step : best,
  );
  return (
    <div className="map__scale">
      <span>{metres >= 1000 ? `${metres / 1000} km` : `${metres} m`}</span>
      <div className="map__scale-bar" style={{ width: `${metres / mpp}px` }} />
    </div>
  );
}

export function WalkMap(props: Props) {
  const { site, origin, baseLayer, colourLayer, points, selectedTargetId } = props;
  const [containerRef, size, setSize] = useSize<HTMLDivElement>();
  const [viewState, setViewState] = useState<MapViewState | null>(null);

  // Frame the walk area once the map knows its size.
  useEffect(() => {
    if (viewState || !size.width || !size.height) return;
    const fit = zoomToFit(WALK_LIMIT_M * 2.2, Math.min(size.width, size.height));
    setViewState({ longitude: 0, latitude: 0, zoom: fit, pitch: 0, bearing: 0 });
  }, [size, viewState]);

  // Fly to a science target when it is picked.
  useEffect(() => {
    const target = site.science_targets.find((candidate) => candidate.id === selectedTargetId);
    if (!target) return;
    const [longitude, latitude] = toLngLat(target.position, origin);
    setViewState((current) =>
      current && {
        ...current,
        longitude,
        latitude,
        transitionDuration: 700,
        transitionInterpolator: new FlyToInterpolator(),
      },
    );
  }, [selectedTargetId, site, origin]);

  // Frame the chosen route when it arrives.
  const { fitTo } = props;
  useEffect(() => {
    if (!fitTo?.length || !size.width || !size.height) return;
    const xs = fitTo.map((point) => point.x);
    const ys = fitTo.map((point) => point.y);
    const centre = { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 200);
    const [longitude, latitude] = toLngLat(centre, origin);
    setViewState((current) =>
      current && {
        ...current,
        longitude,
        latitude,
        zoom: zoomToFit(span * FIT_PADDING, Math.min(size.width, size.height)),
        transitionDuration: 700,
        transitionInterpolator: new FlyToInterpolator(),
      },
    );
    // Only a new set of points re-frames the view; resizing keeps the user's view.
  }, [fitTo, origin]);

  // Follow the crew, heading up, until the user drags the map; Recenter follows again.
  const { crew } = props;
  const [following, setFollowing] = useState(true);
  useEffect(() => {
    if (!crew || !following) return;
    const [longitude, latitude] = toLngLat(crew.position, origin);
    setViewState(
      (current) =>
        current && {
          ...current,
          longitude,
          latitude,
          zoom: FOLLOW_ZOOM,
          pitch: FOLLOW_PITCH,
          bearing: crew.heading,
        },
    );
  }, [crew, following, origin]);

  const viewport = useMemo(
    () =>
      viewState && size.width && size.height
        ? new WebMercatorViewport({ ...viewState, width: size.width, height: size.height })
        : null,
    [viewState, size],
  );

  const { routes } = props;
  const layers = useMemo(() => {
    if (!viewport) return [];
    // Alternatives first, then the chosen route on top with a dark outline.
    const ordered = [...routes].sort((a, b) => Number(a.chosen) - Number(b.chosen));
    const routeLayers = ordered.flatMap((route) => {
      const path = route.path.map((point) => toLngLat(point, origin));
      const line = (id: string, color: number[], width: number) =>
        new PathLayer<{ path: LngLat[] }>({
          id,
          data: [{ path }],
          getPath: (d) => d.path,
          getColor: color as [number, number, number],
          getWidth: width,
          widthUnits: "pixels",
          capRounded: true,
          jointRounded: true,
        });
      return route.chosen
        ? [line(`${route.id}-outline`, OUTLINE_COLOUR, 9), line(route.id, ROUTE_COLOUR, 5)]
        : [line(route.id, ALTERNATIVE_COLOUR, 4)];
    });
    return [
      ...(baseLayer ? rasterLayers(baseLayer, site, viewport, origin, props.fileUrl, 1) : []),
      ...(colourLayer
        ? rasterLayers(colourLayer, site, viewport, origin, props.fileUrl, COLOUR_OPACITY)
        : []),
      ...routeLayers,
      ...(crew
        ? [
            new ScatterplotLayer<CrewPosition>({
              id: "uncertainty-circle",
              data: [crew],
              getPosition: (d) => toLngLat(d.position, origin),
              getRadius: (d) => d.uncertainty_m,
              radiusUnits: "meters",
              getFillColor: (d) => [...LEVEL_COLOURS[d.level], 60],
              getLineColor: (d) => LEVEL_COLOURS[d.level],
              stroked: true,
              lineWidthUnits: "pixels",
              getLineWidth: 2,
            }),
          ]
        : []),
    ];
  }, [viewport, baseLayer, colourLayer, site, origin, props.fileUrl, routes, crew]);

  const project = (point: Point) => {
    const [x = 0, y = 0] = viewport?.project(toLngLat(point, origin)) ?? [];
    return { left: x, top: y };
  };

  const walkLimit = useMemo(() => {
    if (!viewport) return "";
    return Array.from({ length: 121 }, (_, index) => {
      const angle = (index / 120) * 2 * Math.PI;
      const ring: LngLat = toLngLat(
        {
          x: origin.x + WALK_LIMIT_M * Math.sin(angle),
          y: origin.y + WALK_LIMIT_M * Math.cos(angle),
        },
        origin,
      );
      const [x = 0, y = 0] = viewport.project(ring);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [viewport, origin]);

  const change = (patch: Partial<MapViewState>) => {
    setFollowing(false);
    setViewState((current) => current && { ...current, ...patch, transitionDuration: 300 });
  };

  return (
    <div className="map" ref={containerRef}>
      {viewState && (
        <DeckGL
          views={MAP_VIEW}
          viewState={viewState}
          onViewStateChange={({ viewState: next, interactionState }) => {
            if (interactionState.isDragging || interactionState.isPanning) setFollowing(false);
            setViewState(next as MapViewState);
          }}
          onResize={({ width, height }) => setSize({ width, height })}
          controller={{ dragRotate: true, touchRotate: true }}
          layers={layers}
        />
      )}

      {viewport && (
        <div className="map__overlay">
          <svg width={size.width} height={size.height} aria-hidden="true">
            <polyline
              points={walkLimit}
              fill="none"
              stroke="#f2f5fa"
              strokeWidth={1.5}
              strokeDasharray="10 8"
              opacity={0.6}
            />
          </svg>

          {routes.map((route) => {
            const middle = route.path[Math.floor(route.path.length / 2)];
            return middle ? (
              <span
                key={route.id}
                className={`route-label${route.chosen ? " route-label--on" : ""}`}
                style={{ ...project(middle), zIndex: route.chosen ? 6 : 5 }}
              >
                {route.label}
              </span>
            ) : null;
          })}

          {points.checkpoints &&
            site.checkpoints.map((checkpoint, index) => (
              <div key={checkpoint.id} className="marker" style={project(checkpoint.position)}>
                <div className="symbol-checkpoint" title={checkpoint.id}>
                  {index + 1}
                </div>
              </div>
            ))}

          {points.habitatAndCamp && site.habitat && (
            <div className="marker" style={{ ...project(site.habitat), zIndex: 7 }}>
              <div className="symbol-habitat">
                <HouseIcon />
              </div>
              <span className="marker__label">Habitat</span>
            </div>
          )}
          {points.habitatAndCamp && site.base_camp && (
            <div className="marker" style={{ ...project(site.base_camp), zIndex: 7 }}>
              <div className="symbol-camp">
                <FlagIcon />
              </div>
              <span className="marker__label">Base camp</span>
            </div>
          )}

          {points.targets &&
            site.science_targets.map((target) => {
              const selected = target.id === selectedTargetId;
              return (
                <button
                  key={target.id}
                  type="button"
                  className="marker marker--clickable"
                  style={{ ...project(target.position), zIndex: selected ? 9 : 8 }}
                  onClick={() => props.onSelectTarget(target.id)}
                  aria-label={target.name}
                >
                  <div className={`symbol-target${selected ? " symbol-target--selected" : ""}`} />
                  <span className="marker__label">{target.name}</span>
                </button>
              );
            })}

          {props.pair && (
            <>
              <svg className="pair-line" width={size.width} height={size.height} aria-hidden="true">
                <line
                  x1={project(props.pair.predicted).left}
                  y1={project(props.pair.predicted).top}
                  x2={project(props.pair.truth).left}
                  y2={project(props.pair.truth).top}
                  stroke="#f2f5fa"
                  strokeWidth={2}
                  strokeDasharray="6 5"
                />
              </svg>
              <div className="marker" style={{ ...project(props.pair.truth), zIndex: 9 }}>
                <span className="symbol-true" />
                <span className="marker__label">True position</span>
              </div>
              <div className="marker" style={{ ...project(props.pair.predicted), zIndex: 10 }}>
                <span className="position-dot" />
                <span className="marker__label">Fix · {props.pair.label}</span>
              </div>
            </>
          )}

          {crew && (
            <div className="marker" style={{ ...project(crew.position), zIndex: 10 }}>
              <span className="position-dot" />
              <span className={`position-chip position-chip--${crew.level}`}>
                <span className="position-chip__light" />
                {crew.chip}
              </span>
            </div>
          )}
        </div>
      )}

      {colourLayer && (
        <span className="map__badge label">
          {colourLayer.name} · {formatResolution(colourLayer.resolution_m)}
        </span>
      )}

      <div className="map__controls">
        {crew && !following && (
          <button type="button" className="control control--wide" onClick={() => setFollowing(true)}>
            Recenter
          </button>
        )}
        {!crew && (
          <button
            type="button"
            aria-label="Layers"
            className={`control${props.layersOpen ? " control--on" : ""}`}
            onClick={props.onToggleLayers}
          >
            <LayersIcon />
          </button>
        )}
        <button
          type="button"
          aria-label="North up"
          className="control"
          onClick={() => change({ bearing: 0 })}
        >
          <span style={{ display: "flex", transform: `rotate(${-(viewState?.bearing ?? 0)}deg)` }}>
            <NorthIcon />
          </span>
        </button>
        <div className="map__zoom">
          <button
            type="button"
            aria-label="Zoom in"
            className="control"
            onClick={() => change({ zoom: (viewState?.zoom ?? 0) + 1 })}
          >
            <PlusIcon />
          </button>
          <button
            type="button"
            aria-label="Zoom out"
            className="control"
            onClick={() => change({ zoom: (viewState?.zoom ?? 0) - 1 })}
          >
            <MinusIcon />
          </button>
        </div>
        <button
          type="button"
          aria-label="2D or 3D"
          className={`control${viewState?.pitch ? " control--on" : ""}`}
          onClick={() => change({ pitch: viewState?.pitch ? 0 : TILT_DEGREES })}
        >
          3D
        </button>
      </div>

      {baseLayer && (
        <span className="map__caption label" style={{ color: "var(--ink)" }}>
          {baseLayer.title} · {baseLayer.source[0].name} ·{" "}
          {formatResolution(baseLayer.resolution_m)} · {WALK_LIMIT_M / 1000} km walk limit dashed
        </span>
      )}
      {viewState && <ScaleBar zoom={viewState.zoom} />}
      {props.status && <div className="map__status">{props.status}</div>}
    </div>
  );
}
