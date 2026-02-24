EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "parcelRefs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parcelId": {"type": "string"},
                    "rawText": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["parcelId", "rawText", "page"],
            },
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fieldKey": {"type": "string"},
                    "value": {},
                    "unit": {"type": ["string", "null"]},
                    "rawText": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "bbox": {"type": ["array", "null"]},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                },
                "required": [
                    "fieldKey",
                    "value",
                    "rawText",
                    "page",
                    "confidence",
                    "status",
                ],
            },
        },
    },
    "required": ["parcelRefs", "fields"],
}
