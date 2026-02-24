import json
import os
import urllib.request
from urllib.error import HTTPError

from utils.extraction_rules import FIELD_DEFINITIONS
from services.location_extractor import extract_location


def _ai_mode():
    return os.getenv("AI_EXTRACTION_MODE", "llm").strip().lower()


def is_llm_enabled():
    return _ai_mode() in {"llm", "llm_strict", "hybrid"}


def is_llm_strict():
    return _ai_mode() == "llm_strict"


def _llm_config():
    base_url = (os.getenv("OLLAMA_BASE_URL") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("Brak OLLAMA_BASE_URL do ekstrakcji AI.")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    timeout_s = float(os.getenv("OLLAMA_TIMEOUT_S", "40"))
    return base_url, model, timeout_s


def _build_prompt():
    field_specs = []
    for field in FIELD_DEFINITIONS:
        unit = field.get("unit")
        if unit:
            field_specs.append(f"- {field['fieldKey']} (unit: {unit})")
        else:
            field_specs.append(f"- {field['fieldKey']}")
    field_list = "\n".join(field_specs)
    return (
        "Jesteś asystentem analizującym dokumenty MPZP/WZ. "
        "Zwróć WYŁĄCZNIE poprawny JSON (bez dodatkowego tekstu). "
        "Jeżeli wartości nie ma lub nie jesteś pewien, ustaw null. "
        "Jednostki zapisuj zgodnie z poleceniem, a wartości liczbowe zwracaj jako liczby.\n\n"
        "Wymagany format:\n"
        "{\n"
        '  "parcelId": string | null,\n'
        '  "obreb": string | null,\n'
        '  "street": string | null,\n'
        '  "locality": string | null,\n'
        '  "fields": {\n'
        '     "<fieldKey>": { "value": any | null, "unit": string | null, "confidence": number | null }\n'
        "  }\n"
        "}\n\n"
        "Lista fieldKey:\n"
        f"{field_list}\n"
    )


def _build_payload(text, model):
    system_prompt = _build_prompt()
    return {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }


def _ollama_base_url(base_url: str) -> str:
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def _call_ollama_chat(payload, base_url, timeout_s):
    ollama_payload = {
        "model": payload["model"],
        "messages": payload["messages"],
        "stream": False,
    }
    data = json.dumps(ollama_payload).encode("utf-8")
    request = urllib.request.Request(
        f"{_ollama_base_url(base_url)}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    content = parsed["message"]["content"]
    return json.loads(content)


def _call_llm(payload):
    base_url, _, timeout_s = _llm_config()
    try:
        return _call_ollama_chat(payload, base_url, timeout_s)
    except HTTPError as exc:
        if exc.code == 404:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{_ollama_base_url(base_url)}/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = response.read().decode("utf-8")
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"]
            return json.loads(content)
        raise


def extract_structured_data(text):
    _, model, _ = _llm_config()
    payload = _build_payload(text, model)
    return _call_llm(payload)


def build_extraction_from_llm(pages):
    text = "\n".join(
        f"[STRONA {page.get('page')}]\n{page.get('text', '')}" for page in pages
    )
    payload = extract_structured_data(text)
    fields_payload = payload.get("fields") or {}

    fields = []
    for definition in FIELD_DEFINITIONS:
        field_key = definition["fieldKey"]
        unit = definition.get("unit")
        llm_entry = fields_payload.get(field_key) or {}
        value = llm_entry.get("value")
        confidence = llm_entry.get("confidence")
        unit_value = llm_entry.get("unit") or unit
        status = "EXTRACTED" if value is not None else "REQUIRES_REVIEW"
        confidence_value = (
            float(confidence)
            if status == "EXTRACTED" and confidence is not None
            else (0.75 if status == "EXTRACTED" else 0.0)
        )
        fields.append(
            {
                "fieldKey": field_key,
                "value": value if status == "EXTRACTED" else None,
                "unit": unit_value,
                "rawText": "",
                "page": None,
                "bbox": None,
                "confidence": confidence_value,
                "status": status,
            }
        )

    parcel_id = payload.get("parcelId")
    obreb = payload.get("obreb")
    street = payload.get("street")
    locality = payload.get("locality")

    parcel_refs = (
        [{"parcelId": parcel_id, "rawText": "", "page": None}] if parcel_id else []
    )
    obreb_refs = [{"obreb": obreb, "rawText": "", "page": None}] if obreb else []
    street_refs = [{"street": street, "rawText": "", "page": None}] if street else []
    locality_refs = (
        [{"locality": locality, "rawText": "", "page": None}] if locality else []
    )

    return {
        "parcelRefs": parcel_refs,
        "obrebRefs": obreb_refs,
        "streetRefs": street_refs,
        "localityRefs": locality_refs,
        "fields": fields,
    }


def _build_parcel_prompt():
    return (
        "Jesteś ekspertem od analizy dokumentów geodezyjnych i planistycznych. "
        "Masz wywnioskować dane działki z treści dokumentu, nawet gdy etykiety są nietypowe "
        "lub brakuje ich wprost. Dokument może być wynikiem OCR i zawierać błędy.\n"
        "Dokumenty mogą obejmować MPZP, WZ, wypisy z rejestru gruntów, mapy ewidencyjne "
        "lub skany decyzji administracyjnych.\n"
        "Zwróć WYŁĄCZNIE poprawny JSON zgodny ze schematem. "
        "Jeżeli nie jesteś pewien, zwróć null i podaj krótkie uzasadnienie.\n\n"
        "Definicje pól:\n"
        "- parcel_id: numer działki ewidencyjnej (np. 12/3, 45/7, 123/4). Szukaj etykiet "
        "„działka nr”, „nr działki”, „dz.”, „działka ewidencyjna”.\n"
        "- obreb: obręb ewidencyjny/geodezyjny (np. 0123). Szukaj etykiet „obręb”, „obr.”, "
        "„nr obrębu”, „obręb ewidencyjny”.\n"
        "- ulica: nazwa ulicy/adres (np. „ul. Kwiatowa 12”). Szukaj etykiet „ul.”, "
        "„ulica”, „aleja”, „plac”, „adres”.\n"
        "- miejscowosc: miejscowość/miasto/wieś (np. „Kraków”). Szukaj etykiet "
        "„miejscowość”, „miasto”, „m.”. Nie zwracaj „gmina” jako miejscowość, "
        "chyba że to jedyna informacja o lokalizacji.\n\n"
        "Schemat odpowiedzi:\n"
        "{\n"
        '  "parcel_id": { "value": string | null, "confidence": number, "justification": string },\n'
        '  "obreb": { "value": string | null, "confidence": number, "justification": string },\n'
        '  "ulica": { "value": string | null, "confidence": number, "justification": string },\n'
        '  "miejscowosc": { "value": string | null, "confidence": number, "justification": string },\n'
        '  "overall_confidence": number\n'
        "}\n"
    )


def _build_parcel_payload(text, model):
    system_prompt = _build_parcel_prompt()
    return {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }


def _normalize_llm_value(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = " ".join(value.split()).strip(" ,;")
    return cleaned or None


def extract_parcel_inference(text):
    _, model, _ = _llm_config()
    payload = _build_parcel_payload(text, model)
    return _call_llm(payload)



def _build_parcel_inference_from_refs(pages):
    location = extract_location(pages)
    parcel_numbers = location.get("parcel_numbers") or []
    parcel_id = parcel_numbers[0] if parcel_numbers else None
    obreb = location.get("precinct")
    street = location.get("street")
    locality = location.get("city")
    evidence = location.get("evidence") or {}
    parcel_raw = evidence.get("parcel_numbers") or ""
    obreb_raw = evidence.get("precinct") or ""
    street_raw = evidence.get("street") or ""
    locality_raw = evidence.get("city") or ""
    confidence = float(location.get("confidence") or 0.0)

    def _entry(value, raw_text):
        return {
            "value": _normalize_llm_value(value),
            "confidence": confidence if value else 0.0,
            "justification": raw_text.strip(),
        }

    return {
        "parcelId": _normalize_llm_value(parcel_id),
        "parcelNumbers": parcel_numbers,
        "obreb": _normalize_llm_value(obreb),
        "street": _normalize_llm_value(street),
        "locality": _normalize_llm_value(locality),
        "details": {
            "parcel_id": _entry(parcel_id, parcel_raw),
            "obreb": _entry(obreb, obreb_raw),
            "ulica": _entry(street, street_raw),
            "miejscowosc": _entry(locality, locality_raw),
            "overall_confidence": confidence if parcel_id or obreb or street or locality else 0.0,
            "notes": location.get("notes") or [],
            "evidence": evidence,
        },
    }


def build_parcel_inference_from_pages(pages, allow_fallback=True):
    text = "\n".join(
        f"[STRONA {page.get('page')}]\n{page.get('text', '')}" for page in pages
    )
    refs_result = _build_parcel_inference_from_refs(pages)
    refs_details = refs_result.get("details") or {}
    refs_confidence = float(refs_details.get("overall_confidence") or 0.0)
    refs_notes = refs_details.get("notes") or []
    refs_is_qualified = "qualified_subject_window" in refs_notes
    refs_has_missing = any(str(note).startswith("missing_") for note in refs_notes)
    refs_has_footer_signal = any(note in {"-footer", "city_fallback_rejected_footer"} for note in refs_notes)

    if (
        refs_result.get("parcelNumbers")
        and refs_result.get("obreb")
        and refs_result.get("locality")
        and refs_confidence >= 0.45
        and refs_is_qualified
        and not refs_has_missing
        and not refs_has_footer_signal
    ):
        return refs_result

    if is_llm_enabled():
        try:
            payload = extract_parcel_inference(text)
        except Exception:
            if not allow_fallback:
                raise
        else:
            def _entry(field_key):
                entry = payload.get(field_key) or {}
                return {
                    "value": _normalize_llm_value(entry.get("value")),
                    "confidence": entry.get("confidence") if entry.get("confidence") is not None else 0.0,
                    "justification": (entry.get("justification") or "").strip(),
                }

            parcel_entry = _entry("parcel_id")
            obreb_entry = _entry("obreb")
            street_entry = _entry("ulica")
            locality_entry = _entry("miejscowosc")
            overall_confidence = (
                payload.get("overall_confidence")
                if payload.get("overall_confidence") is not None
                else 0.0
            )

            return {
                "parcelId": parcel_entry["value"],
                "parcelNumbers": [parcel_entry["value"]] if parcel_entry["value"] else [],
                "obreb": obreb_entry["value"],
                "street": street_entry["value"],
                "locality": locality_entry["value"],
                "details": {
                    "parcel_id": parcel_entry,
                    "obreb": obreb_entry,
                    "ulica": street_entry,
                    "miejscowosc": locality_entry,
                    "overall_confidence": overall_confidence,
                },
            }

    return refs_result
