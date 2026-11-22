import httpx
import pytest
import respx

from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.gallica import GallicaAdapter

ARK = "bpt6k1234567"
MANIFEST = {"label": "Test Book", "sequences": [{"canvases": [
    {"@id": f"https://gallica.bnf.fr/iiif/ark:/12148/{ARK}/canvas/f1"},
    {"@id": f"https://gallica.bnf.fr/iiif/ark:/12148/{ARK}/canvas/f2"},
]}]}


def _mock_ok():
    respx.get(f"https://gallica.bnf.fr/iiif/ark:/12148/{ARK}/manifest.json").mock(return_value=httpx.Response(200, json=MANIFEST))
    respx.get(f"https://gallica.bnf.fr/ark:/12148/{ARK}/f2.texteBrut").mock(return_value=httpx.Response(200, text="Texte de la page deux."))
    respx.get(f"https://gallica.bnf.fr/iiif/ark:/12148/{ARK}/f2/full/full/0/native.jpg").mock(
        return_value=httpx.Response(206, content=b"\xff\xd8", headers={"content-type": "image/jpeg"}))


@pytest.mark.asyncio
@respx.mock
async def test_gallica_get_page_text():
    _mock_ok()
    async with httpx.AsyncClient() as client:
        page = await GallicaAdapter(client).get_page_text(f"{ARK}@2")
    assert page["verified_mapping"] is True
    assert page["contents"] == "Texte de la page deux."
    assert page["digital_frame"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_gallica_document_page_count_from_manifest():
    _mock_ok()
    async with httpx.AsyncClient() as client:
        doc = await GallicaAdapter(client).get_document(f"https://gallica.bnf.fr/ark:/12148/{ARK}")
    assert doc["page_count"] == 2
    assert doc["ark"] == ARK


@pytest.mark.asyncio
@respx.mock
async def test_gallica_verify_original_ok():
    _mock_ok()
    async with httpx.AsyncClient() as client:
        report = await GallicaAdapter(client).verify_original(f"{ARK}@2")
    assert report["status"] == "verified"


@pytest.mark.asyncio
@respx.mock
async def test_gallica_403_is_adapter_error_not_crash():
    respx.get(f"https://gallica.bnf.fr/ark:/12148/{ARK}/f2.texteBrut").mock(return_value=httpx.Response(403, text="denied"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AdapterError):
            await GallicaAdapter(client).get_page_text(f"{ARK}@2")
