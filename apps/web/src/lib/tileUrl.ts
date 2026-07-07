import { getRuntimeConfig } from "./runtimeConfig";

/** True-color: Earth Search's "visual" asset is already a single-file RGB COG. */
export function trueColorTilejsonUrl(visualHref: string): string {
  const params = new URLSearchParams({ url: visualHref });
  return `${getRuntimeConfig().tilerBaseUrl}/cog/WebMercatorQuad/tilejson.json?${params.toString()}`;
}

/**
 * NDVI: red/nir are *separate* COG files per Sentinel-2 item (unlike
 * "visual"), so this goes through the tiler's STAC-item multi-asset reader
 * (services/tiler's /stac router, backed by rio-tiler's STACReader) rather
 * than the plain single-file /cog router.
 */
export function ndviTilejsonUrl(stacItemSelfHref: string): string {
  const params = new URLSearchParams({
    url: stacItemSelfHref,
    expression: "(nir-red)/(nir+red)",
    // Verified against a live tiler + real STAC item: without this, rio-tiler's
    // STACReader raises InvalidExpression ("Could not find any valid assets")
    // because plain asset names in the expression only resolve to bands when
    // asset_as_band is set — this isn't optional, it's required for this
    // expression syntax to work at all.
    asset_as_band: "true",
  });
  params.append("assets", "red");
  params.append("assets", "nir");
  params.append("rescale", "-1,1");
  return `${getRuntimeConfig().tilerBaseUrl}/stac/WebMercatorQuad/tilejson.json?${params.toString()}`;
}
