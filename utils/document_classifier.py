import json
import os
import re
import tempfile
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageOps


DOC_TYPES = ("MPZP_WYPIS_WYRYS", "WZ_DECYZJA", "MPZP_OGOLNY", "INNE")


@dataclass
class Rule:
    label: str
    phrase: str
    weight: int
    fuzzy_threshold: float = 0.84


RULES: List[Rule] = [
    Rule("MPZP_WYPIS_WYRYS", "wypis i wyrys", 150, 0.8),
    Rule("MPZP_WYPIS_WYRYS", "wypis z miejscowego planu", 140, 0.82),
    Rule("MPZP_WYPIS_WYRYS", "wyrys z miejscowego planu", 140, 0.82),
    Rule("MPZP_WYPIS_WYRYS", "miejscowy plan zagospodarowania przestrzennego", 90, 0.78),
    Rule("MPZP_WYPIS_WYRYS", "mpzp", 70, 0.68),
    Rule("MPZP_WYPIS_WYRYS", "ustalenia planu", 40, 0.82),
    Rule("MPZP_WYPIS_WYRYS", "teren oznaczony symbolem", 40, 0.8),
    Rule("WZ_DECYZJA", "decyzja o warunkach zabudowy", 180, 0.8),
    Rule("WZ_DECYZJA", "decyzja o ustaleniu warunkow zabudowy", 180, 0.8),
    Rule("WZ_DECYZJA", "warunki zabudowy", 100, 0.8),
    Rule("WZ_DECYZJA", "ustalam warunki zabudowy", 90, 0.8),
    Rule("WZ_DECYZJA", "na podstawie art 59", 90, 0.8),
    Rule("WZ_DECYZJA", "samorzadowe kolegium odwolawcze", 70, 0.8),
    Rule("WZ_DECYZJA", "sko", 70, 0.66),
    Rule("WZ_DECYZJA", "pouczenie", 30, 0.86),
    Rule("WZ_DECYZJA", "odwolanie", 30, 0.86),
    Rule("MPZP_OGOLNY", "uchwala nr", 160, 0.8),
    Rule("MPZP_OGOLNY", "w sprawie uchwalenia miejscowego planu", 170, 0.8),
    Rule("MPZP_OGOLNY", "dziennik urzedowy wojewodztwa", 170, 0.8),
    Rule("MPZP_OGOLNY", "rada gminy", 60, 0.82),
    Rule("MPZP_OGOLNY", "rada miasta", 60, 0.82),
]


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _strip_polish(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _ocr_tolerant_text(text: str) -> str:
    text = text.lower()
    repl = {
        "1": "i",
        "0": "o",
        "3": "e",
        "4": "a",
        "5": "s",
        "2": "z",
        "8": "b",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return text


def _normalize_text_variants(text: str) -> Dict[str, str]:
    base = _normalize_spaces((text or "").lower())
    plain = _strip_polish(base)
    tolerant = _ocr_tolerant_text(plain)
    return {"base": base, "plain": plain, "tolerant": tolerant}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            rem = prev[j] + 1
            rep = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, rem, rep))
        prev = cur
    return prev[-1]


def fuzzyMatch(haystack: str, needle: str, threshold: float = 0.82) -> float:
    h = _normalize_text_variants(haystack)["tolerant"]
    n = _normalize_text_variants(needle)["tolerant"]
    if not h or not n:
        return 0.0
    if n in h:
        return 1.0

    h_tokens = h.split()
    n_tokens = n.split()
    if not h_tokens or not n_tokens:
        return 0.0

    win = len(n_tokens)
    best = 0.0
    if len(h_tokens) < win:
        dist = _levenshtein(h, n)
        return max(0.0, 1.0 - dist / max(len(h), len(n), 1))

    target = " ".join(n_tokens)
    for i in range(0, len(h_tokens) - win + 1):
        chunk = " ".join(h_tokens[i : i + win])
        dist = _levenshtein(chunk, target)
        sim = max(0.0, 1.0 - dist / max(len(chunk), len(target), 1))
        if sim > best:
            best = sim
            if best >= threshold:
                return best
    return best


def ocrTopRegionWithTesseract(image: Image.Image, lang: str = "pol") -> str:
    try:
        import pytesseract
    except ModuleNotFoundError:
        return ""

    try:
        prepared = ImageOps.grayscale(image)
        prepared = ImageOps.autocontrast(prepared)
        return pytesseract.image_to_string(prepared, lang=lang, config="--psm 6") or ""
    except Exception:
        try:
            return pytesseract.image_to_string(image, lang="pol+eng", config="--psm 6") or ""
        except Exception:
            return ""


def _open_image_with_heic_support(file_path: str) -> Image.Image:
    try:
        import pillow_heif  # type: ignore

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    return Image.open(file_path)


def extractTopTextFromImage(file_path: str) -> Dict[str, object]:
    with _open_image_with_heic_support(file_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        top_h = max(1, int(height * 0.30))
        top_region = image.crop((0, 0, width, top_h))
        text = ocrTopRegionWithTesseract(top_region, lang="pol")

    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    extracted = _normalize_spaces(" ".join(lines))[:1200]
    return {
        "pages": [{"page": 1, "topText": text, "lines": lines}],
        "extractedTopText": extracted,
    }


def _pdf_top_text_via_render(file_path: str, page_index: int) -> str:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(file_path)
        page = pdf[page_index]
        bitmap = page.render(scale=2.0)
        pil = bitmap.to_pil()
        top_h = max(1, int(pil.height * 0.30))
        top = pil.crop((0, 0, pil.width, top_h))
        return ocrTopRegionWithTesseract(top, lang="pol")
    except Exception:
        return ""


def extractTopTextFromPdf(file_path: str) -> Dict[str, object]:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    page_count = len(reader.pages)
    pages_to_check = [0]

    first_text = (reader.pages[0].extract_text() or "") if page_count else ""
    letters = len(re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", first_text))
    if page_count > 1 and letters < 180:
        pages_to_check.append(1)

    page_results = []
    for idx in pages_to_check:
        raw_text = reader.pages[idx].extract_text() or ""
        raw_lines = [ln.strip() for ln in re.split(r"[\r\n]+", raw_text) if ln.strip()]
        top_from_text = "\n".join(raw_lines[:35])
        top_from_ocr = _pdf_top_text_via_render(file_path, idx)

        chosen = top_from_ocr if len(top_from_ocr.strip()) > len(top_from_text.strip()) else top_from_text
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", chosen) if ln.strip()]
        page_results.append({"page": idx + 1, "topText": chosen, "lines": lines})

    extracted = _normalize_spaces(" ".join(page["topText"] for page in page_results))[:1200]
    return {"pages": page_results, "extractedTopText": extracted}


def _line_has_mpzp_context(text: str) -> bool:
    return fuzzyMatch(text, "dzialka nr", 0.78) >= 0.78 or fuzzyMatch(text, "obreb", 0.78) >= 0.78


def scoreTextLines(page_lines: List[Dict[str, object]]) -> Dict[str, object]:
    scores = {"MPZP_WYPIS_WYRYS": 0, "WZ_DECYZJA": 0, "MPZP_OGOLNY": 0}
    evidence_by_type: Dict[str, List[Dict[str, object]]] = {
        "MPZP_WYPIS_WYRYS": [],
        "WZ_DECYZJA": [],
        "MPZP_OGOLNY": [],
    }

    for page in page_lines:
        page_no = int(page.get("page") or 1)
        for line in page.get("lines", []):
            line_text = str(line).strip()
            if not line_text:
                continue

            for rule in RULES:
                sim = fuzzyMatch(line_text, rule.phrase, threshold=rule.fuzzy_threshold)
                if sim < rule.fuzzy_threshold:
                    continue

                line_score = int(round(rule.weight * max(0.72, sim)))
                if rule.label == "MPZP_WYPIS_WYRYS" and _line_has_mpzp_context(line_text):
                    line_score += 25

                scores[rule.label] += line_score
                evidence_by_type[rule.label].append(
                    {
                        "page": page_no,
                        "text": line_text,
                        "matched": [rule.phrase],
                        "score": line_score,
                    }
                )

            if fuzzyMatch(line_text, "mpzp", 0.68) >= 0.68 and "§" in line_text:
                scores["MPZP_OGOLNY"] += 60
                evidence_by_type["MPZP_OGOLNY"].append(
                    {
                        "page": page_no,
                        "text": line_text,
                        "matched": ["§", "mpzp"],
                        "score": 60,
                    }
                )

            if fuzzyMatch(line_text, "wypis", 0.76) >= 0.76 or fuzzyMatch(line_text, "wyrys", 0.76) >= 0.76:
                scores["MPZP_OGOLNY"] -= 180
                evidence_by_type["MPZP_OGOLNY"].append(
                    {
                        "page": page_no,
                        "text": line_text,
                        "matched": ["wypis/wyrys (kara dla MPZP_OGOLNY)"],
                        "score": -180,
                    }
                )

    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_label, top_score = ranking[0]
    second_score = ranking[1][1] if len(ranking) > 1 else 0

    needs_llm = False
    if top_score < 200:
        needs_llm = True
    if top_score >= 220 and second_score >= 220 and abs(top_score - second_score) < 60:
        needs_llm = True

    return {
        "scores": scores,
        "winner": top_label,
        "winnerScore": top_score,
        "secondScore": second_score,
        "needsLlm": needs_llm,
        "evidenceByType": evidence_by_type,
    }


def _extract_json_from_text(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except Exception:
            return None
    return None


def callOllamaFallback(extractedTopText: str, best_lines: List[str]) -> Optional[dict]:
    base_url = (os.getenv("OLLAMA_BASE_URL") or "").rstrip("/")
    if not base_url:
        return None
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    timeout_s = float(os.getenv("OLLAMA_TIMEOUT_S", "35"))

    clipped = (extractedTopText or "")[:2500]
    joined_lines = "\n".join(f"- {ln}" for ln in best_lines[:8])
    prompt = (
        "Sklasyfikuj dokument planistyczny do jednej z etykiet: "
        "MPZP_WYPIS_WYRYS, WZ_DECYZJA, MPZP_OGOLNY, INNE. "
        "Zwróć WYŁĄCZNIE JSON o schemacie: "
        '{"label":"...","confidence":0..1,"rationale":"...","key_lines":["...","..."]}.\n\n'
        "Tekst nagłówka (OCR):\n"
        f"{clipped}\n\n"
        "Najbardziej istotne linie:\n"
        f"{joined_lines}\n"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        content = (parsed.get("message") or {}).get("content", "")
        result = _extract_json_from_text(content)
        if not result:
            return None
        label = str(result.get("label") or "INNE").upper().strip()
        if label not in DOC_TYPES:
            label = "INNE"
        confidence = float(result.get("confidence") or 0.0)
        key_lines = result.get("key_lines") or []
        if not isinstance(key_lines, list):
            key_lines = []
        return {
            "label": label,
            "confidence": max(0.0, min(1.0, confidence)),
            "rationale": str(result.get("rationale") or ""),
            "key_lines": [str(v) for v in key_lines if str(v).strip()],
        }
    except Exception:
        return None


def _similarity(a: str, b: str) -> float:
    a_n = _normalize_text_variants(a)["tolerant"]
    b_n = _normalize_text_variants(b)["tolerant"]
    if not a_n or not b_n:
        return 0.0
    dist = _levenshtein(a_n, b_n)
    return max(0.0, 1.0 - dist / max(len(a_n), len(b_n), 1))


def _map_llm_lines_to_evidence(key_lines: List[str], page_lines: List[Dict[str, object]]) -> List[Dict[str, object]]:
    candidates = []
    for line in key_lines:
        best = None
        best_sim = 0.0
        for page in page_lines:
            for src in page.get("lines", []):
                sim = _similarity(line, str(src))
                if sim > best_sim:
                    best_sim = sim
                    best = {"page": int(page.get("page") or 1), "text": str(src)}
        if best and best_sim >= 0.5:
            candidates.append(
                {
                    "page": best["page"],
                    "text": best["text"],
                    "matched": [line],
                    "score": int(round(best_sim * 100)),
                }
            )
    return candidates


def _ocr_quality_penalty(extracted_top_text: str) -> float:
    text = extracted_top_text or ""
    letters = len(re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", text))
    digits = len(re.findall(r"\d", text))
    non_space = len(re.sub(r"\s+", "", text))
    if non_space < 60 or letters < 35:
        return 0.15
    if non_space > 0 and (letters + digits) / non_space < 0.55:
        return 0.15
    return 0.0


def classifyDocument(filePath_or_buffer, mimeType: Optional[str] = None, filename: Optional[str] = None) -> Dict[str, object]:
    temp_path = None
    try:
        if isinstance(filePath_or_buffer, (bytes, bytearray)):
            suffix = Path(filename or "upload.bin").suffix or ".bin"
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            handle.write(filePath_or_buffer)
            handle.flush()
            handle.close()
            temp_path = handle.name
            file_path = temp_path
        else:
            file_path = str(filePath_or_buffer)

        ext = Path(filename or file_path).suffix.lower()
        mime = (mimeType or "").lower()
        is_pdf = ext == ".pdf" or mime == "application/pdf"

        if is_pdf:
            top = extractTopTextFromPdf(file_path)
        else:
            top = extractTopTextFromImage(file_path)

        page_lines = top.get("pages") or []
        extracted_top_text = str(top.get("extractedTopText") or "")[:1200]
        scores_result = scoreTextLines(page_lines)

        winner = str(scores_result["winner"])
        winner_score = int(scores_result["winnerScore"])
        evidence_by_type = scores_result["evidenceByType"]

        winner_evidence = sorted(
            evidence_by_type.get(winner, []),
            key=lambda item: item.get("score", 0),
            reverse=True,
        )[:8]
        if len(winner_evidence) > 3:
            winner_evidence = winner_evidence[:8]

        if scores_result["needsLlm"] or len(extracted_top_text) < 120:
            top_lines = [item.get("text", "") for item in winner_evidence[:6]]
            llm = callOllamaFallback(extracted_top_text[:2500], top_lines)
            if llm and llm.get("confidence", 0.0) >= 0.65:
                winner = llm["label"]
                winner_score = max(winner_score, int(round(float(llm["confidence"]) * 420)))
                mapped = _map_llm_lines_to_evidence(llm.get("key_lines") or [], page_lines)
                if mapped:
                    winner_evidence = mapped[:8]

        if winner not in DOC_TYPES:
            winner = "INNE"
        if winner_score < 1 and winner != "INNE":
            winner = "INNE"

        confidence = min(1.0, winner_score / 420.0)
        confidence = max(0.0, confidence - _ocr_quality_penalty(extracted_top_text))

        return {
            "fileType": winner,
            "confidence": round(confidence, 3),
            "evidence": winner_evidence[:8],
            "extractedTopText": extracted_top_text,
        }
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
