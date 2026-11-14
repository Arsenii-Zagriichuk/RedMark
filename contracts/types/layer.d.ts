/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Metadata for one map layer, in $REDMARK_DATA/<site>/layers/<name>/layer.json, next to its tiles. Owners: Person 2 (layer groups 1 to 3), Person 3 (group 5).
 */
export interface LayerMeta {
  /**
   * Same as the layer's folder name.
   */
  name: string;
  /**
   * Display name.
   */
  title: string;
  /**
   * Layer group: 1 base, 2 walkability, 3 science, 4 conditions, 5 location quality.
   */
  group: number;
  /**
   * Units of the values the colours stand for; empty for a photo.
   */
  units: string;
  /**
   * Ground size of one full-resolution pixel, in metres. The app shows it in the legend.
   */
  resolution_m: number;
  bounds: Bounds;
  tiles: Tiles;
  /**
   * @minItems 1
   */
  legend: [LegendEntry, ...LegendEntry[]];
  /**
   * @minItems 1
   */
  source: [LayerSource, ...LayerSource[]];
}
/**
 * A rectangle in map metres.
 */
export interface Bounds {
  /**
   * West edge.
   */
  min_x: number;
  /**
   * South edge.
   */
  min_y: number;
  /**
   * East edge.
   */
  max_x: number;
  /**
   * North edge.
   */
  max_y: number;
}
/**
 * Image tiles in map metres. At max_zoom one pixel is resolution_m; each lower zoom halves the resolution. Tile (x, y) counts from the north-west corner of bounds.
 */
export interface Tiles {
  /**
   * Tile path template relative to the layer folder, e.g. tiles/{z}/{x}/{y}.png.
   */
  path: string;
  /**
   * Tile width and height in pixels.
   */
  tile_size: number;
  min_zoom: number;
  max_zoom: number;
}
/**
 * One legend row.
 */
export interface LegendEntry {
  /**
   * Text shown.
   */
  label: string;
  /**
   * Hex colour.
   */
  color: string;
  /**
   * The value this colour stands for, if the layer is continuous.
   */
  value?: number;
}
/**
 * A data set the layer was made from; also listed in a data manifest.
 */
export interface LayerSource {
  /**
   * Name of the data set.
   */
  name: string;
  /**
   * Where it came from.
   */
  url: string;
}
