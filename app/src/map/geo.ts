// Map maths in local metres. Every position in the contracts is map metres in the site's
// own projection. The map lays them out as metres east and north of the habitat, placed at
// 0° N 0° E on deck.gl's Web Mercator map, where a degree is the same length both ways.
import type { LayerMeta } from "@contracts/layer";
import type { Point } from "@contracts/site";

/** The walk area reaches 2 km from the habitat (GLOSSARY.md, "Walk area"). */
export const WALK_LIMIT_M = 2000;

const EARTH_CIRCUMFERENCE_M = 2 * Math.PI * 6378137;
const METRES_PER_DEGREE = EARTH_CIRCUMFERENCE_M / 360;
const DECK_TILE_PX = 512;

export type LngLat = [number, number];

export function toLngLat(point: Point, origin: Point): LngLat {
  return [(point.x - origin.x) / METRES_PER_DEGREE, (point.y - origin.y) / METRES_PER_DEGREE];
}

export function fromLngLat([lng, lat]: LngLat, origin: Point): Point {
  return { x: origin.x + lng * METRES_PER_DEGREE, y: origin.y + lat * METRES_PER_DEGREE };
}

/** Ground metres per screen pixel at a deck.gl zoom, near 0° N. */
export function metresPerPixel(zoom: number): number {
  return EARTH_CIRCUMFERENCE_M / (DECK_TILE_PX * 2 ** zoom);
}

/** The deck.gl zoom at which a span of metres fills a span of pixels. */
export function zoomToFit(metres: number, pixels: number): number {
  return Math.log2(EARTH_CIRCUMFERENCE_M / (DECK_TILE_PX * (metres / pixels)));
}

/** Distance in metres and bearing in degrees from map north, between two map points. */
export function distanceAndBearing(from: Point, to: Point) {
  const east = to.x - from.x;
  const north = to.y - from.y;
  const bearing = (Math.atan2(east, north) * 180) / Math.PI;
  return { metres: Math.hypot(east, north), bearing: (bearing + 360) % 360 };
}

/** Ground distance: "985 m", "1.21 km", "2 km". */
export function formatDistance(metres: number): string {
  return metres < 1000 ? `${Math.round(metres)} m` : `${Number((metres / 1000).toFixed(2))} km`;
}

export function formatBearing(degrees: number): string {
  return `${String(Math.round(degrees) % 360).padStart(3, "0")}°`;
}

/** Latitude and longitude text for a map point, when the site uses an equirectangular map. */
export function formatLatLon(point: Point, projection: string): string | null {
  const params = new Map(
    projection
      .split(/\s+/)
      .filter((part) => part.startsWith("+"))
      .map((part) => {
        const [key = "", value = ""] = part.slice(1).split("=");
        return [key, value] as const;
      }),
  );
  const radius = Number(params.get("R"));
  if (params.get("proj") !== "eqc" || !radius) return null;
  const latTs = (Number(params.get("lat_ts") ?? 0) * Math.PI) / 180;
  const lon0 = Number(params.get("lon_0") ?? 0);
  const lat = ((point.y / radius) * 180) / Math.PI;
  const lon = lon0 + ((point.x / (radius * Math.cos(latTs))) * 180) / Math.PI;
  const latText = `${Math.abs(lat).toFixed(4)}° ${lat < 0 ? "S" : "N"}`;
  const lonText = `${Math.abs(lon).toFixed(4)}° ${lon < 0 ? "W" : "E"}`;
  return `${latText} ${lonText}`;
}

export interface Tile {
  key: string;
  url: string;
  /** West, south, east, north in map metres. */
  bounds: [number, number, number, number];
}

/** The tile zoom whose pixels are closest to (not coarser than) the screen's. */
export function tileZoomFor(layer: LayerMeta, screenMetresPerPixel: number): number {
  const { min_zoom, max_zoom } = layer.tiles;
  const steps = Math.floor(Math.log2(screenMetresPerPixel / layer.resolution_m));
  return Math.min(max_zoom, Math.max(min_zoom, max_zoom - steps));
}

/**
 * The tiles of a layer at one zoom that overlap a rectangle in map metres. Per layer.json:
 * at max_zoom one pixel is resolution_m, each lower zoom halves the resolution, and tile
 * (x, y) counts from the north-west corner of the layer's bounds.
 */
export function tilesIn(
  layer: LayerMeta,
  zoom: number,
  view: { west: number; south: number; east: number; north: number },
  url: (path: string) => string,
): Tile[] {
  const { bounds, tiles } = layer;
  const tileMetres = tiles.tile_size * layer.resolution_m * 2 ** (tiles.max_zoom - zoom);
  const columns = Math.ceil((bounds.max_x - bounds.min_x) / tileMetres);
  const rows = Math.ceil((bounds.max_y - bounds.min_y) / tileMetres);
  const clamp = (value: number, count: number) => Math.min(count - 1, Math.max(0, value));
  const firstX = clamp(Math.floor((view.west - bounds.min_x) / tileMetres), columns);
  const lastX = clamp(Math.floor((view.east - bounds.min_x) / tileMetres), columns);
  const firstY = clamp(Math.floor((bounds.max_y - view.north) / tileMetres), rows);
  const lastY = clamp(Math.floor((bounds.max_y - view.south) / tileMetres), rows);
  if (view.east < bounds.min_x || view.west > bounds.max_x) return [];
  if (view.north < bounds.min_y || view.south > bounds.max_y) return [];
  const found: Tile[] = [];
  for (let x = firstX; x <= lastX; x++) {
    for (let y = firstY; y <= lastY; y++) {
      const west = bounds.min_x + x * tileMetres;
      const north = bounds.max_y - y * tileMetres;
      const path = tiles.path
        .replace("{z}", String(zoom))
        .replace("{x}", String(x))
        .replace("{y}", String(y));
      found.push({
        key: `${layer.name}/${zoom}/${x}/${y}`,
        url: url(path),
        bounds: [west, north - tileMetres, west + tileMetres, north],
      });
    }
  }
  return found;
}

/** A layer's ground resolution as the legend states it, e.g. "0.25 m" or "15.6 m". */
export function formatResolution(metres: number): string {
  return `${Number(metres.toPrecision(3))} m`;
}
