import json
import re
import sys
from typing import Dict, List, Optional

import fitz
import pytesseract
from PIL import Image


DEFAULT_PAGES = 2
DEFAULT_DPI = 250


def render_pdf_to_images(file_path: str, max_pages: int = DEFAULT_PAGES, dpi: int = DEFAULT_DPI) -> List[Image.Image]:
    doc = fitz.open(file_path)
    images: List[Image.Image] = []
    try:
        page_count = min(max_pages, doc.page_count)
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        for page_index in range(page_count):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(image)
    finally:
        doc.close()
    return images


def detect_text_layer(pdf_path: str) -> bool:
    doc = fitz.open(pdf_path)
    try:
        if doc.page_count == 0:
            return False
        page = doc.load_page(0)
        text = page.get_text("text").strip()
        return len(text) >= 30
    finally:
        doc.close()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x09\x0B-\x1F\x7F]", "", text)
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def ocr_pages(pdf_path: str, pages: int = DEFAULT_PAGES, dpi: int = DEFAULT_DPI) -> List[str]:
    images = render_pdf_to_images(pdf_path, max_pages=pages, dpi=dpi)
    texts: List[str] = []
    for image in images:
        raw_text = pytesseract.image_to_string(image, lang="pol")
        texts.append(normalize_text(raw_text))
    return texts


def normalize_parcel_number(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return re.sub(r"\s*/\s*", "/", value.strip())


def normalize_obreb(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value)
    return cleaned.strip()


def normalize_ulica(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.;")
    cleaned = re.sub(r"\s+\d{2}-\d{3}.*$", "", cleaned)
    cleaned = re.sub(
        r"\s+\b(?:miejscowo(?:ść|sc)|miasto|gm\.?|gmina|obr[eę]b|dzielnic\w*)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.split(",")[0]
    cleaned = re.split(r"\s+w\s+dzielnic\w*\s+.*", cleaned, flags=re.IGNORECASE)[0]
    return cleaned.strip(" ,.;")


def normalize_miejscowosc(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" .,")
    cleaned = re.sub(r"\s+\d{2}-\d{3}.*$", "", cleaned)
    cleaned = re.sub(
        r"\s+\b(?:gmina|gm\.?|powiat|wojew[oó]dztwo|obr[eę]b)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.split(",")[0]
    if cleaned.lower().startswith("warszaw") and cleaned.lower().endswith("wie"):
        return "Warszawa"
    return cleaned


def extract_fallback(context: str) -> Dict[str, Optional[str]]:
    parcel_match = re.search(
        r"(?:działk\w*|dzialk\w*).*?nr\s*(?:ew\.?|ewid\.?|ewidencyjn\w*)?\s*(\d+(?:\s*/\s*\d+)?)",
        context,
        re.IGNORECASE | re.DOTALL,
    )
    obreb_match = re.search(
        r"obr[ęe]b\w*(?:\s+nr)?\s*(\d{1,2}(?:-\d{1,2}){2}|\d{4,6}|"
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż\- ]{2,50})",
        context,
        re.IGNORECASE,
    )
    street_match = re.search(
        r"((?:\b(?:ul|al|pl|os)\b\.?|\b(?:ulica|aleje?|plac|osiedle)\b)\s*[:\-]?\s*"
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż0-9\-\. ]{2,80}?)"
        r"(?=\s*(?:,|\n|$|\b\d{2}-\d{3}\b|\bw\s+dzielnic\w*\b|\b(?:miejscowość|miejscowosc|miasto|gm\.|gmina|obr[eę]b)\b))",
        context,
        re.IGNORECASE,
    )
    postal_match = re.search(
        r"\d{2}-\d{3}\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż\- ]{2,60})",
        context,
    )
    w_matches = list(
        re.finditer(
            r"\bw\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż\- ]{2,60})",
            context,
        )
    )
    locality_value = None
    if postal_match:
        locality_value = postal_match.group(1)
    elif w_matches:
        locality_value = w_matches[-1].group(1)

    return {
        "numer_dzialki": parcel_match.group(1) if parcel_match else None,
        "obreb": obreb_match.group(1) if obreb_match else None,
        "ulica": street_match.group(1) if street_match else None,
        "miejscowosc": locality_value,
    }


def find_key_sentence(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.search(r"działk|dzialk", line, re.IGNORECASE) and re.search(r"obr", line, re.IGNORECASE):
            context_lines = [line]
            for offset in range(1, 3):
                if index + offset < len(lines):
                    context_lines.append(lines[index + offset])
            return " ".join(context_lines)
    return None


def extract_city_from_postal(text: str) -> Optional[str]:
    match = re.search(
        r"\b\d{2}-\d{3}\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż\- ]{2,60})",
        text,
    )
    if match:
        return match.group(1).strip()
    return None


def extract_fields_from_sentence(sentence: str) -> Dict[str, Optional[str]]:
    parcel_match = re.search(
        r"(?:działk\w*|dzialk\w*).*?nr\s*(?:ew\.?)?\s*(\d+(?:\s*/\s*\d+)?)",
        sentence,
        re.IGNORECASE,
    )
    obreb_match = re.search(
        r"obr[ęe]b\w*\s+nr\s*(\d{1,2}(?:-\d{1,2}){2})",
        sentence,
        re.IGNORECASE,
    )
    street_match = re.search(
        r"przy\s+(?P<ulica>(?:\b(?:ul|al|pl|os)\b\.?|\b(?:ulica|aleja|plac|osiedle)\b)"
        r"\s*[:\-]?\s*[^,.\n]+?)(?:\s+w\b|,|\.|\b\d{2}-\d{3}\b|$)",
        sentence,
        re.IGNORECASE,
    )
    locality_matches = list(
        re.finditer(
            r"\bw\s+([A-Za-zĄĆĘŁŃÓŚŹŻąęćłńóśźż\-]+)",
            sentence,
        )
    )
    locality = locality_matches[-1].group(1) if locality_matches else None

    return {
        "numer_dzialki": parcel_match.group(1) if parcel_match else None,
        "obreb": obreb_match.group(1) if obreb_match else None,
        "ulica": street_match.group("ulica") if street_match else None,
        "miejscowosc": locality,
    }


def build_result(
    values: Dict[str, Optional[str]],
    confidence: Dict[str, float],
    sentence: str,
    page_number: int,
    debug: Dict[str, object],
) -> Dict[str, object]:
    return {
        "numer_dzialki": normalize_parcel_number(values.get("numer_dzialki")),
        "obreb": normalize_obreb(values.get("obreb")),
        "ulica": normalize_ulica(values.get("ulica")),
        "miejscowosc": normalize_miejscowosc(values.get("miejscowosc")),
        "confidence": confidence,
        "evidence": {
            "sentence": sentence.strip(),
            "page": page_number,
        },
        "debug": debug,
    }


def extract_from_texts(
    texts: List[str],
    debug: Dict[str, object],
) -> Dict[str, object]:
    evidence_sentence = None
    evidence_page = 1
    for page_index, text in enumerate(texts, start=1):
        sentence = find_key_sentence(text)
        if sentence:
            evidence_sentence = sentence
            evidence_page = page_index
            break

    if evidence_sentence:
        extracted = extract_fields_from_sentence(evidence_sentence)
        full_text = "\n".join(texts)
        postal_city = extract_city_from_postal(full_text)
        if postal_city:
            extracted["miejscowosc"] = postal_city
        confidence = {
            "numer_dzialki": 0.9 if extracted.get("numer_dzialki") else 0.0,
            "obreb": 0.9 if extracted.get("obreb") else 0.0,
            "ulica": 0.8 if extracted.get("ulica") else 0.0,
            "miejscowosc": 0.7 if extracted.get("miejscowosc") else 0.0,
        }
        return build_result(extracted, confidence, evidence_sentence, evidence_page, debug)

    full_text = "\n".join(texts)
    fallback_values = extract_fallback(full_text)
    if not any(fallback_values.values()):
        debug["why"] = "no key sentence found"
    confidence = {
        "numer_dzialki": 0.6 if fallback_values.get("numer_dzialki") else 0.0,
        "obreb": 0.6 if fallback_values.get("obreb") else 0.0,
        "ulica": 0.6 if fallback_values.get("ulica") else 0.0,
        "miejscowosc": 0.6 if fallback_values.get("miejscowosc") else 0.0,
    }
    return build_result(fallback_values, confidence, "", 1, debug)


def extract_fields(file_path: str, max_pages: int = DEFAULT_PAGES) -> Dict[str, object]:
    debug: Dict[str, object] = {
        "used_ocr": False,
        "text_layer": False,
        "pages": [],
        "ocr_text_len": [],
        "ocr_preview": [],
    }
    text_layer = detect_text_layer(file_path)
    debug["text_layer"] = text_layer

    try:
        doc = fitz.open(file_path)
    except Exception:
        debug["why"] = "unable to open pdf"
        return build_result({}, {}, "", 1, debug)

    texts: List[str] = []
    try:
        page_count = min(max_pages, doc.page_count)
        debug["pages"] = list(range(1, page_count + 1))
        if text_layer:
            for page_index in range(page_count):
                page = doc.load_page(page_index)
                texts.append(normalize_text(page.get_text("text")))
        else:
            debug["used_ocr"] = True
            ocr_texts = ocr_pages(file_path, pages=page_count, dpi=DEFAULT_DPI)
            texts = ocr_texts
            debug["ocr_text_len"] = [len(text) for text in ocr_texts]
            debug["ocr_preview"] = [text[:200] for text in ocr_texts]
    except pytesseract.TesseractNotFoundError:
        debug["used_ocr"] = True
        debug["why"] = "tesseract missing"
        return build_result({}, {}, "", 1, debug)
    finally:
        doc.close()

    return extract_from_texts(texts, debug)


def main() -> None:
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "/mnt/data/SKMBT_C28022122212430.pdf"
    result = extract_fields(file_path)
    debug_info = result.get("debug", {})
    evidence = result.get("evidence", {})
    sys.stderr.write(
        "DEBUG: used_ocr={used_ocr} text_layer={text_layer} pages={pages} ocr_text_len={ocr_text_len}\n".format(
            used_ocr=debug_info.get("used_ocr"),
            text_layer=debug_info.get("text_layer"),
            pages=debug_info.get("pages"),
            ocr_text_len=debug_info.get("ocr_text_len"),
        )
    )
    sys.stderr.write(f"DEBUG: evidence='{evidence.get('sentence', '')}'\n")
    if debug_info.get("why"):
        sys.stderr.write(f"DEBUG: why='{debug_info.get('why')}'\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
