from services.wfs_response_parser import WfsServiceError, detect_wfs_response_format, parse_wfs_payload


def test_detect_and_parse_geojson():
    body = '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[1,1],[2,1],[2,2],[1,1]]]},"properties":{"numer_dzialki":"12/3"}}]}'
    parsed = parse_wfs_payload(response_headers={"Content-Type": "application/json"}, response_body=body)
    assert detect_wfs_response_format({"Content-Type": "application/json"}, body) == "json"
    assert len(parsed["features"]) == 1


def test_parse_gml_feature_collection():
    body = """<?xml version='1.0'?>
    <wfs:FeatureCollection xmlns:wfs='http://www.opengis.net/wfs' xmlns:gml='http://www.opengis.net/gml' xmlns:egib='urn:egib'>
      <gml:featureMember>
        <egib:dzialka fid='dz.1'>
          <egib:numer_dzialki>100/2</egib:numer_dzialki>
          <egib:geom>
            <gml:Polygon><gml:outerBoundaryIs><gml:LinearRing><gml:coordinates>1,1 2,1 2,2 1,2 1,1</gml:coordinates></gml:LinearRing></gml:outerBoundaryIs></gml:Polygon>
          </egib:geom>
        </egib:dzialka>
      </gml:featureMember>
    </wfs:FeatureCollection>
    """
    parsed = parse_wfs_payload(response_headers={"Content-Type": "text/xml"}, response_body=body)
    assert len(parsed["features"]) == 1
    assert parsed["features"][0]["properties"]["numer_dzialki"] == "100/2"


def test_xml_exception_report_returns_service_error():
    body = "<ExceptionReport><Exception exceptionCode='InvalidParameterValue'><ExceptionText>invalid parameter value</ExceptionText></Exception></ExceptionReport>"
    try:
        parse_wfs_payload(response_headers={"Content-Type": "application/xml"}, response_body=body)
    except WfsServiceError as exc:
        assert exc.error_type == "service_exception"
        assert "invalid parameter value" in str(exc)
    else:
        raise AssertionError("Expected WfsServiceError")


def test_xml_service_exception_report_returns_service_error():
    body = "<ServiceExceptionReport><ServiceException>bad typename</ServiceException></ServiceExceptionReport>"
    try:
        parse_wfs_payload(response_headers={"Content-Type": "text/xml"}, response_body=body)
    except WfsServiceError as exc:
        assert exc.error_type == "service_exception"
    else:
        raise AssertionError("Expected WfsServiceError")


def test_html_response_is_detected_as_error():
    body = "<html><body>proxy error</body></html>"
    try:
        parse_wfs_payload(response_headers={"Content-Type": "text/html"}, response_body=body)
    except WfsServiceError as exc:
        assert exc.error_type == "html_response"
    else:
        raise AssertionError("Expected WfsServiceError")


def test_empty_response_is_error():
    try:
        parse_wfs_payload(response_headers={"Content-Type": "application/xml"}, response_body="")
    except WfsServiceError as exc:
        assert exc.error_type == "empty_response"
    else:
        raise AssertionError("Expected WfsServiceError")


def test_wrong_content_type_but_xml_body_is_supported():
    body = "<wfs:FeatureCollection xmlns:wfs='http://www.opengis.net/wfs'></wfs:FeatureCollection>"
    parsed = parse_wfs_payload(response_headers={"Content-Type": "text/plain"}, response_body=body)
    assert parsed["type"] == "FeatureCollection"


def test_wrong_content_type_but_json_body_is_supported():
    body = '{"type":"FeatureCollection","features":[]}'
    parsed = parse_wfs_payload(response_headers={"Content-Type": "text/plain"}, response_body=body)
    assert parsed["features"] == []
