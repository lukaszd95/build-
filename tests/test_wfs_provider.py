import json
from unittest.mock import patch

from services.map_service import ParcelProvider, normalizeParcelInput


class _MockResponse:
    def __init__(self, status=200, body=""):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _provider():
    return ParcelProvider(
        {
            "provider": "wfs",
            "wfs": {
                "url": "https://example.test/wfs",
                "typeName": "dzialki",
                "version": "2.0.0",
                "mapping": {
                    "parcelNumber": {"type": "singleField", "field": "numer_dzialki"},
                    "obreb": {"field": "obreb"},
                },
            },
        }
    )


def test_fetch_wfs_features_retries_with_discovered_namespaced_typename():
    provider = _provider()
    normalized = normalizeParcelInput("123/4", "0001", "Warszawa")

    capabilities = """<?xml version='1.0' encoding='UTF-8'?>
    <WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs/2.0'>
      <wfs:FeatureTypeList>
        <wfs:FeatureType><wfs:Name>egib:dzialki</wfs:Name></wfs:FeatureType>
      </wfs:FeatureTypeList>
    </WFS_Capabilities>
    """

    def fake_urlopen(request, timeout=15):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "GetCapabilities" in url:
            return _MockResponse(body=capabilities)
        if "typeNames=dzialki" in url:
            raise RuntimeError("Invalid type name")
        if "typeNames=egib%3Adzialki" in url:
            return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}))
        raise AssertionError(url)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        features = provider._fetch_wfs_features(provider.config["wfs"], normalized)

    assert features == []


def test_wfs_request_json_raises_service_exception_on_xml_error_response():
    provider = _provider()
    xml_error = "<ServiceExceptionReport><ServiceException>boom</ServiceException></ServiceExceptionReport>"

    with patch("urllib.request.urlopen", return_value=_MockResponse(body=xml_error)):
        try:
            provider._wfs_request_json(url="https://example.test/wfs", params={"service": "WFS"}, timeout=5)
        except RuntimeError as exc:
            assert "wyjątek" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")


def test_build_cql_filter_uses_precinct_variants():
    provider = _provider()
    normalized = normalizeParcelInput("137", "3-15-11", "Warszawa")

    cql = provider._build_cql_filter(provider.config["wfs"]["mapping"], normalized)

    assert "numer_dzialki='137'" in cql
    assert "obreb='3-15-11'" in cql
    assert "obreb='31511'" in cql
    assert "obreb='0011'" in cql
