# IIIF integration (b5)

`src/global_library_mcp/iiif.py` is the single place that parses
IIIF so adapters do not re-implement it:

- `parse_manifest(payload)` - Presentation API **v2**
  (sequences/canvases, `@id`, `seeAlso` OCR links, `license`)
  and **v3** (`items`, language-map labels, `rights`,
  annotation-page image bodies and supplementing annotations).
  Each canvas yields: index, canvas_id, label, image_service_id,
  image_url, ocr_urls, dimensions.
- `alto_to_text(xml)` - bounded, namespace-agnostic ALTO XML to
  text (TextLine/String order). Malformed XML raises, so a broken
  fetch is a failure, not an empty page.
- `hocr_to_text(html)` - hOCR to text via a real HTML parser
  (word spans nest inside line spans; the previous regex approach
  silently dropped words - found by the b5 fixtures).

## Provenance rules

- The printed page label and the digital frame number are kept
  separate everywhere (`printed_page` vs `digital_frame`).
- A canvas/OCR pairing is *proven* only when the manifest or the
  provider's documented pattern links them AND the OCR payload
  corroborates it (e.g. MDZ: canvas id + image-service suffix +
  hOCR title). Otherwise `verified_mapping` is false.
- Manifests are untrusted input: URLs taken from them are only
  fetched through the shared budgeted client, and file names are
  never trusted as paths (see the IA adapter's traversal guard).
- There is deliberately NO "fetch any IIIF manifest URL" tool:
  an arbitrary-URL fetcher would be an SSRF surface. Each
  adapter builds manifest URLs from its own fixed API base and
  a validated record id.
