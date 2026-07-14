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

/**
 * SAR amplitude (grayscale): Sentinel-1 GRD has no bundled RGB composite
 * like optical's "visual" -- vv/vh are each a single-band COG (same
 * multi-asset STAC-item shape as NDVI's red/nir), so this goes through the
 * same /stac router. rescale is a documented starting point for Earth
 * Search's typical uint16 GRD digital-number range, not independently
 * verified against a live tile fetch in this sandbox (no outbound network
 * available here) -- see IMAGERY_UX_FIXES_REPORT.md's verification-limits
 * convention. Recalibrate against a real scene before relying on it.
 */
export function sarAmplitudeTilejsonUrl(stacItemSelfHref: string): string {
  const params = new URLSearchParams({ url: stacItemSelfHref, rescale: "0,5000" });
  params.append("assets", "vv");
  return `${getRuntimeConfig().tilerBaseUrl}/stac/WebMercatorQuad/tilejson.json?${params.toString()}`;
}

/**
 * SAR false color: R=VV, G=VH, B=VV/VH ratio -- a standard dual-pol SAR
 * composite (water/smooth surfaces read dark, vegetation/rough surfaces
 * read green-ish, urban/corner-reflector returns read bright). Same
 * unverified-rescale caveat as sarAmplitudeTilejsonUrl above.
 */
export function sarFalseColorTilejsonUrl(stacItemSelfHref: string): string {
  const params = new URLSearchParams({
    url: stacItemSelfHref,
    expression: "vv;vh;vv/vh",
    asset_as_band: "true",
    rescale: "0,5000;0,2000;0,5",
  });
  params.append("assets", "vv");
  params.append("assets", "vh");
  return `${getRuntimeConfig().tilerBaseUrl}/stac/WebMercatorQuad/tilejson.json?${params.toString()}`;
}
