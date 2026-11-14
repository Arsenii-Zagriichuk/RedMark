/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Every external data file one owner uses, in <owner folder>/data-manifest.yaml. The project page's References field is built from these.
 */
export interface DataManifest {
  files: ManifestFile[];
}
/**
 * One data file.
 */
export interface ManifestFile {
  /**
   * What the file is.
   */
  name: string;
  /**
   * Path relative to REDMARK_DATA.
   */
  path: string;
  size_bytes: number;
  /**
   * Where it was downloaded from.
   */
  source_url: string;
  /**
   * The checksum value.
   */
  checksum: string;
  /**
   * e.g. sha256, or md5-s3-multipart for a USGS S3 ETag.
   */
  checksum_algorithm: string;
  /**
   * Citation or licence for References, if the source asks for one.
   */
  credit?: string;
}
