import io
import json
import urllib.error
from unittest.mock import patch

from services.map_service import ParcelProvider, normalizeParcelInput


class _MockResponse:
    def __init__(self, status=200, body="", content_type="application/json"):
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}

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

    def fake_open(request, timeout=15):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "GetCapabilities" in url:
            return _MockResponse(body=capabilities, content_type="text/xml")
        if "typeNames=dzialki" in url:
            raise RuntimeError("Invalid type name")
        if "typeNames=egib%3Adzialki" in url:
            return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}))
        raise AssertionError(url)

    class _Opener:
        def open(self, request, timeout=15):
            return fake_open(request, timeout)

    with patch("urllib.request.build_opener", return_value=_Opener()):
        features, _diag = provider._fetch_wfs_features(provider.config["wfs"], normalized)

    assert features == []


def test_wfs_request_json_raises_service_exception_on_xml_error_response():
    provider = _provider()
    xml_error = "<ServiceExceptionReport><ServiceException>boom</ServiceException></ServiceExceptionReport>"

    class _Opener:
        def open(self, request, timeout=15):
            return _MockResponse(body=xml_error, content_type="text/xml")

    with patch("urllib.request.build_opener", return_value=_Opener()):
        try:
            provider._wfs_request_json(url="https://example.test/wfs", params={"service": "WFS"}, timeout=5)
        except RuntimeError as exc:
            assert "błąd usługi" in str(exc)
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


def test_fetch_wfs_features_falls_back_without_cql_filter_when_filtered_requests_fail():
    provider = _provider()
    normalized = normalizeParcelInput("137", "3-15-11", "Warszawa")

    def fake_open(request, timeout=15):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "GetCapabilities" in url:
            return _MockResponse(
                body="""<?xml version='1.0'?><WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs/2.0'><wfs:FeatureTypeList><wfs:FeatureType><wfs:Name>dzialki</wfs:Name></wfs:FeatureType></wfs:FeatureTypeList></WFS_Capabilities>""",
                content_type="text/xml",
            )
        if "CQL_FILTER=" in url:
            return _MockResponse(body="<html><body>blocked</body></html>", content_type="text/html")
        return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}), content_type="application/json")

    class _Opener:
        def open(self, request, timeout=15):
            return fake_open(request, timeout)

    with patch("urllib.request.build_opener", return_value=_Opener()):
        features, diag = provider._fetch_wfs_features(provider.config["wfs"], normalized)

    assert features == []
    assert diag.status_code == 200


def test_wfs_request_json_retries_once_after_502_and_then_succeeds():
    provider = _provider()
    calls = {"count": 0}

    class _Opener:
        def open(self, request, timeout=15):
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError(
                    url=request.full_url,
                    code=502,
                    msg="Bad Gateway",
                    hdrs={"Content-Type": "text/plain"},
                    fp=io.BytesIO(b"bad gateway"),
                )
            return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}))

    with patch("urllib.request.build_opener", return_value=_Opener()), patch("time.sleep") as sleep_mock:
        data, diag = provider._wfs_request_json(url="https://example.test/wfs", params={"service": "WFS"}, timeout=5)

    assert data["features"] == []
    assert diag.status_code == 200
    assert calls["count"] == 2
    sleep_mock.assert_called_once_with(0.2)


def test_fetch_wfs_features_uses_limited_request_variants():
    provider = _provider()
    normalized = normalizeParcelInput("137", "3-15-11", "Warszawa")
    seen_urls: list[str] = []

    def fake_open(request, timeout=15):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        seen_urls.append(url)
        if "GetCapabilities" in url:
            return _MockResponse(
                body="""<?xml version='1.0'?><WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs/2.0'><wfs:FeatureTypeList><wfs:FeatureType><wfs:Name>dzialki</wfs:Name></wfs:FeatureType></wfs:FeatureTypeList></WFS_Capabilities>""",
                content_type="text/xml",
            )
        if "outputFormat=application%2Fjson" in url and "CQL_FILTER=" in url:
            return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}), content_type="application/json")
        raise AssertionError(url)

    class _Opener:
        def open(self, request, timeout=15):
            return fake_open(request, timeout)

    with patch("urllib.request.build_opener", return_value=_Opener()):
        features, _diag = provider._fetch_wfs_features(provider.config["wfs"], normalized)

    assert features == []
    non_capabilities = [url for url in seen_urls if "GetCapabilities" not in url]
    assert all("outputFormat=application%2Fjson" in url or "outputFormat=application%2Fgeo%2Bjson" in url for url in non_capabilities)
    assert all("outputFormat=text%2Fxml" not in url for url in non_capabilities)


def test_wfs_request_json_retries_after_connection_reset_and_then_succeeds():
    provider = _provider()
    calls = {"count": 0}

    class _Opener:
        def open(self, request, timeout=15):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionResetError("Connection reset by peer")
            return _MockResponse(body=json.dumps({"type": "FeatureCollection", "features": []}))

    with patch("urllib.request.build_opener", return_value=_Opener()), patch("time.sleep") as sleep_mock:
        data, diag = provider._wfs_request_json(url="https://example.test/wfs", params={"service": "WFS"}, timeout=5)

    assert data["features"] == []
    assert diag.status_code == 200
    assert calls["count"] == 2
    sleep_mock.assert_called_once_with(0.2)
