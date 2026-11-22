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
