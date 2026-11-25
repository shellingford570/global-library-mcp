import httpx
import pytest
import respx

from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter
from global_library_mcp.service import LibraryService

ITEM = "testitem"
DJVU = "Title page\fChapter one discusses the dam and its turbines at length.\fFinal page"
DJVU_XML = """<DjVuXML><BODY>
<OBJECT width="100" height="200"><LINE><WORD>Title</WORD><WORD>page</WORD></LINE></OBJECT>
<OBJECT width="100" height="200"><LINE><WORD>Chapter</WORD><WORD>one</WORD><WORD>discusses</WORD><WORD>the</WORD><WORD>dam</WORD><WORD>and</WORD><WORD>its</WORD><WORD>turbines</WORD><WORD>at</WORD><WORD>length.</WORD></LINE></OBJECT>
<OBJECT width="100" height="200"><LINE><WORD>Final</WORD><WORD>page</WORD></LINE></OBJECT>
</BODY></DjVuXML>"""
METADATA = {"metadata": {"title": "Test Item", "creator": "A. Uthor", "date": "1909"},
            "files": [{"name": f"{ITEM}_djvu.txt"}, {"name": f"{ITEM}_djvu.xml"}, {"name": f"{ITEM}_scandata.xml"}]}
RESTRICTED = {"metadata": {"title": "Locked", "access-restricted-item": "true"},
              "files": [{"name": "locked_djvu.txt"}]}


def _mock_item(metadata=METADATA, item=ITEM, djvu=DJVU, xml=DJVU_XML):
    respx.get(f"https://archive.org/metadata/{item}").mock(return_value=httpx.Response(200, json=metadata))
    if xml is not None:
        respx.get(f"https://archive.org/download/{item}/{item}_djvu.xml").mock(return_value=httpx.Response(200, text=xml))
    if djvu is not None:
        respx.get(f"https://archive.org/download/{item}/{item}_djvu.txt").mock(return_value=httpx.Response(200, text=djvu))


@pytest.mark.asyncio
@respx.mock
async def test_ia_search_in_document_finds_leaf():
    _mock_item()
    async with httpx.AsyncClient() as client:
        found = await InternetArchiveAdapter(client).search_in_document(ITEM, "dam")
    assert found["matches"]["hit"] == 1
    assert found["matches"]["list"][0]["id"] == "testitem@1"


@pytest.mark.asyncio
@respx.mock
async def test_ia_get_page_text_maps_leaf():
    _mock_item()
    async with httpx.AsyncClient() as client:
        page = await InternetArchiveAdapter(client).get_page_text("testitem@1")
    assert page["verified_mapping"] is True
    assert page["digital_frame"] == 1
    assert "dam and its turbines" in page["contents"]
    assert page["ocr_source"] == "djvu.xml"
    assert page["image_url"] == "https://archive.org/download/testitem/page/n1.jpg"
    assert page["page_count"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_ia_out_of_range_leaf_is_unverified():
    _mock_item()
    async with httpx.AsyncClient() as client:
        page = await InternetArchiveAdapter(client).get_page_text("testitem@99")
    assert page["verified_mapping"] is False
    assert page["contents"] == ""


@pytest.mark.asyncio
@respx.mock
async def test_ia_restricted_item_refuses_full_text():
    _mock_item(metadata=RESTRICTED, item="locked", djvu=None)
    async with httpx.AsyncClient() as client:
        with pytest.raises(AdapterError):
            await InternetArchiveAdapter(client).search_in_document("locked", "dam")


@pytest.mark.asyncio
@respx.mock
async def test_ia_verify_original_all_checks():
    _mock_item()
    respx.get(f"https://archive.org/download/{ITEM}/page/n1.jpg").mock(
        return_value=httpx.Response(206, content=b"\xff\xd8", headers={"content-type": "image/jpeg"}))
    async with httpx.AsyncClient() as client:
        report = await InternetArchiveAdapter(client).verify_original("testitem@1")
    assert report["status"] == "verified"
    assert all(check["ok"] for check in report["checks"].values())


@pytest.mark.asyncio
@respx.mock
async def test_ia_evidence_flows_through_service():
    respx.get("https://archive.org/advancedsearch.php").mock(return_value=httpx.Response(200, json={
        "response": {"docs": [{"identifier": ITEM, "title": "Test Item", "creator": "A. Uthor", "date": "1909"}]}}))
    _mock_item()
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("dam turbines", libraries=["internet-archive"])
    assert len(result["evidence"]) == 1
    evidence = result["evidence"][0]
    assert evidence["citation_key"] == "internet-archive:testitem:testitem@1"
    assert evidence["image_url"].endswith("/page/n1.jpg")


@pytest.mark.asyncio
@respx.mock
async def test_ia_djvu_txt_fallback_when_no_xml():
    txt_only = {"metadata": {"title": "Txt Only"}, "files": [{"name": "txtonly_djvu.txt"}]}
    _mock_item(metadata=txt_only, item="txtonly", xml=None)
    async with httpx.AsyncClient() as client:
        page = await InternetArchiveAdapter(client).get_page_text("txtonly@1")
    assert page["verified_mapping"] is True
    assert page["ocr_source"] == "djvu.txt"


def test_file_name_resolution_from_metadata():
    """Release-prep fix (integration, 2026-11-24): djvu file names must
    come from the metadata file list, not a guessed
    ``{identifier}_djvu.xml`` — multi-volume and renamed items 404'd."""
    from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter

    resolve = InternetArchiveAdapter._file_name
    multi = {"files": [{"name": "UBM_1932_03_04_djvu.xml"}, {"name": "UBM_1932_01_02_djvu.xml"}]}
    assert resolve(multi, "_djvu.xml", "UBM_1932") == "UBM_1932_01_02_djvu.xml"
    renamed = {"files": [{"name": "1872_Origin_F391_djvu.xml"}]}
    assert resolve(renamed, "_djvu.xml", "darwin-online_1872_Origin_F391") == "1872_Origin_F391_djvu.xml"
    exact = {"files": [{"name": "other_djvu.xml"}, {"name": "item1_djvu.xml"}]}
    assert resolve(exact, "_djvu.xml", "item1") == "item1_djvu.xml"
    assert resolve({"files": []}, "_djvu.xml", "x") is None


# --- Section-1 fixes (source accuracy, multi-volume mapping, URL safety) ---

RENAMED_META = {"metadata": {"title": "Origin"}, "files": [{"name": "1872_Origin_F391_djvu.xml"}]}
MULTI_META = {"metadata": {"title": "Multi"},
              "files": [{"name": "multi_01_djvu.xml"}, {"name": "multi_02_djvu.xml"}]}


@pytest.mark.asyncio
@respx.mock
async def test_ia_source_reflects_renamed_xml_file():
    """The reported source must be the file actually fetched, with its
    real name and format — not a guessed {identifier}_djvu.txt."""
    respx.get("https://archive.org/metadata/darwinx").mock(return_value=httpx.Response(200, json=RENAMED_META))
    respx.get("https://archive.org/download/darwinx/1872_Origin_F391_djvu.xml").mock(
        return_value=httpx.Response(200, text=DJVU_XML))
    async with httpx.AsyncClient() as client:
        adapter = InternetArchiveAdapter(client)
        page = await adapter.get_page_text("darwinx@1")
        found = await adapter.search_in_document("darwinx", "dam")
    assert page["ocr_file"] == "1872_Origin_F391_djvu.xml"
    assert page["ocr_source"] == "djvu.xml"
    assert page["source"] == "https://archive.org/download/darwinx/1872_Origin_F391_djvu.xml"
    assert page["verified_mapping"] is True
    assert "djvu.xml" in found["source"] and "1872_Origin_F391_djvu.xml" in found["source"]
    assert "djvu.txt" not in found["source"]


@pytest.mark.asyncio
@respx.mock
async def test_ia_source_reflects_txt_when_txt_is_used():
    txt_only = {"metadata": {"title": "Txt Only"}, "files": [{"name": "txtonly_djvu.txt"}]}
    _mock_item(metadata=txt_only, item="txtonly", xml=None)
    async with httpx.AsyncClient() as client:
        adapter = InternetArchiveAdapter(client)
        page = await adapter.get_page_text("txtonly@1")
        found = await adapter.search_in_document("txtonly", "dam")
    assert page["ocr_source"] == "djvu.txt"
    assert page["source"] == "https://archive.org/download/txtonly/txtonly_djvu.txt"
    assert "djvu.txt" in found["source"]


@pytest.mark.asyncio
@respx.mock
async def test_ia_multivolume_mapping_is_unverified():
    """Multi-volume items: OCR comes from the first file, but its leaf
    numbering cannot be confirmed against the item-wide page images,
    so neither get_page_text nor verify_original may claim verified."""
    respx.get("https://archive.org/metadata/multi").mock(return_value=httpx.Response(200, json=MULTI_META))
    respx.get("https://archive.org/download/multi/multi_01_djvu.xml").mock(
        return_value=httpx.Response(200, text=DJVU_XML))
    respx.get("https://archive.org/download/multi/page/n1.jpg").mock(
        return_value=httpx.Response(206, content=b"\xff\xd8", headers={"content-type": "image/jpeg"}))
    async with httpx.AsyncClient() as client:
        adapter = InternetArchiveAdapter(client)
        page = await adapter.get_page_text("multi@1")
        report = await adapter.verify_original("multi@1")
    assert "dam and its turbines" in page["contents"]
    assert page["verified_mapping"] is False
    assert page["mapping_status"] == "unverified"
    assert "unverified" in page["mapping_note"]
    assert report["status"] != "verified"
    assert report["checks"]["page_mapping"]["ok"] is False


def test_ia_unsafe_file_names_are_not_selected_or_quoted_raw():
    """OCR file names are external data: names with path separators or
    traversal are never selected, and names with spaces or URL-reserved
    characters are percent-encoded in the download URL."""
    resolve = InternetArchiveAdapter._file_name
    hostile = {"files": [{"name": "../evil_djvu.xml"}, {"name": "sub/dir_djvu.xml"}, {"name": "safe_djvu.xml"}]}
    assert resolve(hostile, "_djvu.xml", "item") == "safe_djvu.xml"
    adapter = InternetArchiveAdapter.__new__(InternetArchiveAdapter)
    url = adapter._download_url("item", "my file?x=1_djvu.xml")
    assert url == "https://archive.org/download/item/my%20file%3Fx%3D1_djvu.xml"


@pytest.mark.asyncio
@respx.mock
async def test_ia_multivolume_pages_are_not_verified_evidence_in_service():
    """End-to-end gate: multi-volume IA pages must land in the
    service's `unverified` bucket, never in verified evidence — so
    the Web UI, MCP tools, answers and comparisons built on
    collect_evidence cannot present them as verified."""
    respx.get("https://archive.org/advancedsearch.php").mock(return_value=httpx.Response(200, json={
        "response": {"docs": [{"identifier": "multi", "title": "Multi", "creator": "A. Uthor", "date": "1909"}]}}))
    respx.get("https://archive.org/metadata/multi").mock(return_value=httpx.Response(200, json=MULTI_META))
    respx.get("https://archive.org/download/multi/multi_01_djvu.xml").mock(
        return_value=httpx.Response(200, text=DJVU_XML))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("dam turbines", libraries=["internet-archive"])
    ia_verified = [e for e in result["evidence"] if e["library_id"] == "internet-archive"]
    ia_unverified = [u for u in result["unverified"] if u.get("library_id") == "internet-archive"]
    assert ia_verified == []
    assert len(ia_unverified) >= 1
