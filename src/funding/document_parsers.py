"""Extract complete source text and documentary links; originals are always retained.

No LLM summarisation, script execution or application-form submissions.
OCR derivatives are labelled and never replace the original file.
"""
import copy
import hashlib
import io
import json
import re
import threading
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree
from pypdf import PdfReader

from funding.adapters import eura_data

PARSER_VERSION = "5"
DOCUMENT = re.compile(r"\.(pdf|doc[xm]?|xls[xm]?|ppt[xm]?|odt|ods|odp|rtf|zip)(?:$|[?#])", re.I)
RELEVANT = re.compile(
    r"ehto|my.nt.perust|arviointiperust|valintaperust|hakuohje|liite|hakuilmoit|hakukuulut|"
    r"lis.tieto|tarkemmat.tiedot|ulkoinenAsiointipalveluUrl|usein[\s_-]+kysyt|"
    r"kysymy(?:kset|ksi[aä])[\s_-]+ja[\s_-]+vastau|vastau\w*[\s_-]+kysym|"
    r"rahoitusohje|avustusohje|hakeminen|rahoituksen-hak|"
    r"general.terms|terms.and.conditions|conditions|eligibil|criteri|guideline|guidance|annex|appendi|"
    r"call.document|call.text|call.for.proposal|work.programme|reference.document|faq|"
    r"questions?[\s_-]+(?:and[\s_-]+)?answers?|fr[åa]gor[\s_-]+och[\s_-]+svar|"
    r"further.?information|more.?information|supporting.document|application.guide|application.form|dossier|"
    r"funding.rules|financial.regulation|model.grant|f.rordning|villkor|anvisning|bilag",
    re.I,
)
INFORMATION_LINK = re.compile(
    r"programme[\s_/-]+manual|programme[\s_/-]+region[\s_/-]+map|call[\s_-]+calendar|"
    r"funding/checklist|/rahoitus/haut/|esityslist|p[öo]yt[äa]kir|kokousaineisto", re.I)
NAVIGATION = re.compile(
    r"privacy|cookies?|tietosuoja|saavutettavuusseloste|accessibility.statement|"
    r"/login|/signin|/sign-in|kirjaudu|/wp-json|/wp-admin|/api/yllapito|/api/avustus(?:hakemus|asia)|"
    r"facebook.com|linkedin.com|twitter.com|youtube.com|instagram.com|subscribe|newsletter", re.I,
)


def document_url(url, base=""):
    try:
        url = urljoin(base, url.strip()).replace("&amp;", "&")
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        return None
    if len(url) > 2048:
        return None
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    # Original href remains in the archived response; only tracking and fragments are removed.
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", urlencode(query), ""))


@dataclass
class Link:
    url: str
    title: str = ""
    role: str = "reference"
    follow: bool = False
    parser: str = "web"


@dataclass
class Parsed:
    text: str = ""
    title: str = ""
    status: str = "extracted"
    flags: list[str] = field(default_factory=list)
    page_count: int | None = None
    links: list[Link] = field(default_factory=list)
    link_inputs: list[tuple[str, str, bool, str]] = field(default_factory=list, repr=False)


def infer_media_type(body, declared):
    if body.startswith(b"%PDF-"):
        return "application/pdf"
    if body.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" in names and archive.getinfo("[Content_Types].xml").file_size <= 1_000_000:
                    content_types = archive.read("[Content_Types].xml").lower()
                    for application in ("word.document", "excel.sheet", "powerpoint.presentation"):
                        marker = ("application/vnd.ms-"+application+".macroenabled.main+xml").encode()
                        if marker in content_types:
                            return "application/vnd.ms-"+application+".macroenabled.12"
                for name, kind in (("word/document.xml", "wordprocessingml.document"),
                                   ("xl/workbook.xml", "spreadsheetml.sheet"),
                                   ("ppt/presentation.xml", "presentationml.presentation")):
                    if name in names:
                        return "application/vnd.openxmlformats-officedocument."+kind
        except zipfile.BadZipFile:
            pass
    return declared


def add_link(result, href, title, base, mandatory=False, parser="web"):
    result.link_inputs.append((href, title, mandatory, parser))
    url = document_url(href, base)
    if not url and href.strip().startswith(("https://", "http://")):
        result.flags.append("malformed_source_url:"+href[:300])
        if mandatory or DOCUMENT.search(href) or RELEVANT.search(title):
            result.status = "partial_text"
    if not url or url == document_url(base):
        return
    label = title[:1000]
    follow = mandatory or bool((DOCUMENT.search(url) or RELEVANT.search(label+" "+url) or INFORMATION_LINK.search(label+" "+url))
                               and not NAVIGATION.search(label+" "+url))
    role = "required_section" if mandatory else "attachment" if DOCUMENT.search(url) else "reference"
    result.links.append(Link(url, label, role, follow, parser))


def html_part(value, result, base):
    soup = BeautifulSoup(value, "html.parser")
    for node in soup.select("template"):
        node.unwrap()
    soup = BeautifulSoup(str(soup), "html.parser")  # TemplateString needs reparsing.
    for node in soup.select("script,style,nav,footer,header,form,noscript"):
        node.decompose()
    for link in soup.select("a[href]"):
        title = link.get_text(" ", strip=True)
        # A short label such as "here" can point to the actual conditions or Q&A.
        # Use only its bounded local paragraph/list item, never the whole page.
        parent = link.find_parent(["p", "li", "dd"])
        if parent is not None and len(title) <= 80 and len(parent.select("a[href]")) <= 2:
            context = parent.get_text(" ", strip=True)
            if len(context) <= 1000 and RELEVANT.search(context) and not RELEVANT.search(title+" "+link["href"]):
                title = title+" · "+context
        add_link(result, link["href"], title, base)
    for picture in soup.select("img[src]"):
        title = picture.get("alt", "")
        if INFORMATION_LINK.search(title+" "+picture["src"]):
            add_link(result, picture["src"], title, base, mandatory=True)
    return soup.get_text("\n", strip=True)


def json_text(value, result, base, path=""):
    """Keep all fields and languages, including rich-text editor JSON and empty values."""
    if isinstance(value, dict):
        if isinstance(value.get("url"), str):
            add_link(result, value["url"], str(value.get("text", value.get("title", path))), base)
        if isinstance(value.get("href"), str):
            add_link(result, value["href"], str(value.get("text", path)), base)
        return "\n".join(json_text(v, result, base, f"{path}.{k}".lstrip(".")) for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(json_text(v, result, base, f"{path}[{i}]") for i, v in enumerate(value)) or path+": []"
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return json_text(json.loads(value), result, base, path)
            except (ValueError, RecursionError):
                pass
        for url in re.findall(r'https?://[^\s<>"\x27]+', value):
            add_link(result, url.rstrip(".,);"), path, base)
        return path+": "+(html_part(value, result, base) if "<" in value else value)
    return path+": "+json.dumps(value, ensure_ascii=False)


def referenced_codes(notice, codes):
    references = set()
    def visit(value):
        if isinstance(value, dict):
            references.update(map(str, value))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif value is not None:
            references.add(str(value))
    visit(notice)
    return {category: {key: label for key, label in values.items() if str(key) in references}
            for category, values in codes.items() if isinstance(values, dict)
            and any(str(key) in references for key in values)}


_PDF_CACHE = OrderedDict()
_PDF_CACHE_BYTES = 0
_PDF_CACHE_LOCK = threading.Lock()
_PDF_CACHE_LIMIT = 64*1024*1024


def parse_document(body, media_type, url, parser="web"):
    """Reuse identical PDF derivatives, resolving relative links for each actual source URL."""
    global _PDF_CACHE_BYTES
    is_pdf = body.startswith(b"%PDF-") or media_type.split(";", 1)[0] == "application/pdf"
    key = (hashlib.sha256(body).hexdigest(), parser, PARSER_VERSION) if is_pdf else None
    if key:
        with _PDF_CACHE_LOCK:
            cached = _PDF_CACHE.get(key)
            if cached:
                _PDF_CACHE.move_to_end(key)
                result = copy.deepcopy(cached[0])
                references, result.links, result.link_inputs = result.link_inputs, [], []
                for href, title, mandatory, mode in references:
                    add_link(result, href, title, url, mandatory=mandatory, parser=mode)
                unique = {}
                for link in result.links:
                    if link.url not in unique or link.follow:
                        unique[link.url] = link
                result.links = list(unique.values())
                result.flags = list(dict.fromkeys(result.flags))
                return result
    result = _parse_document(body, media_type, url, parser)
    if key:
        size = 4*(len(result.text)+sum(len(link.url)+len(link.title) for link in result.links)
                  +sum(len(href)+len(title)+len(mode) for href, title, _, mode in result.link_inputs)
                  +sum(map(len, result.flags)))+4096
        if size <= _PDF_CACHE_LIMIT:
            with _PDF_CACHE_LOCK:
                previous = _PDF_CACHE.pop(key, None)
                if previous:
                    _PDF_CACHE_BYTES -= previous[1]
                while _PDF_CACHE and _PDF_CACHE_BYTES+size > _PDF_CACHE_LIMIT:
                    _PDF_CACHE_BYTES -= _PDF_CACHE.popitem(last=False)[1][1]
                _PDF_CACHE[key] = (copy.deepcopy(result), size)
                _PDF_CACHE_BYTES += size
    return result


def _parse_document(body, media_type, url, parser="web"):
    result = Parsed()
    media_type = media_type.split(";", 1)[0].lower()
    if parser in ("hae_json", "eu_json") or media_type == "application/json":
        data = json.loads(body)
        if not isinstance(data, (dict, list)) or not data or (isinstance(data, dict) and ("error" in data or "errors" in data)):
            raise ValueError("Expected published funding content; empty/error JSON is not call evidence")
        result.text = json_text(data, result, url)
        if parser == "hae_json" and isinstance(data, dict) and data.get("hasVakioehdot"):
            prefix = url.split("/hakuilmoitus/", 1)[0]
            for section in ("yleista", "lahtokohdat", "ehdot", "velvollisuudet", "valvonta"):
                add_link(result, prefix+"/vakioehdot/"+section, "Vakioehdot: "+section, url,
                         mandatory=True, parser="hae_json")
        if parser == "hae_json" and isinstance(data, dict) and data.get("isHakulomakePreviewEligible"):
            prefix = url.split("/hakuilmoitus/", 1)[0]
            for section in ("HakijanTiedot", "TavoitteetJaVaikuttavuus", "ToiminnanToteutus", "KustannusarvioJaRahoitus"):
                add_link(result, prefix+"/hakemuslomake/"+section, "Julkinen lomake-esikatselu: "+section, url,
                         mandatory=True, parser="hae_json")
    elif parser == "eura":
        data = eura_data(body.decode("utf-8"))
        notice = data.get("ilmoitus")
        if not isinstance(notice, dict) or not notice.get("otsikko") or "kuvaus" not in notice:
            raise ValueError("Full EURA notice is absent")
        result.title = notice["otsikko"]
        result.text = json_text({"ilmoitus": notice, "referenced_code_labels": referenced_codes(
            notice, data.get("koodisto", {}))}, result, url)
    elif body.startswith(b"%PDF-") or media_type == "application/pdf":
        pdf = PdfReader(io.BytesIO(body), strict=False)
        if pdf.is_encrypted and pdf.decrypt("") == 0:
            result.status, result.flags = "unreadable", ["encrypted_pdf"]
            return result
        result.page_count = len(pdf.pages)
        pages, empty = [], []
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            pages.append(f"[Page {i}]\n{text}")
            if len(text.strip()) < 20:
                empty.append(i)
            for annotation in page.get("/Annots", []):
                try:
                    action = annotation.get_object().get("/A", {})
                    if action.get("/URI"):
                        add_link(result, str(action["/URI"]), "PDF reference", url)
                except (AttributeError, TypeError, ValueError):
                    result.flags.append("unparsed_pdf_annotation")
            for href in re.findall(r'https?://[^\s<>"\x27]+', text):
                add_link(result, href.rstrip(".,);"), "PDF text reference", url)
        result.text = "\n\n".join(pages)
        if empty:
            result.status = "partial_text"
            result.flags.append("pages_need_visual_or_ocr_review:"+",".join(map(str, empty)))
            from funding.ocr import read_scan_pages
            recognized, flags = read_scan_pages(body, empty)
            result.flags.extend(flags)
            for page, text in recognized.items():
                pages[page-1] += "\n[OCR; verify against original]\n"+text
                for href in re.findall(r'https?://[^\s<>"\x27]+', text):
                    add_link(result, href.rstrip(".,);"), "OCR reference; verify", url)
            result.text = "\n\n".join(pages)
    elif body.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.infolist()
            if len(members) > 5000 or sum(m.file_size for m in members) > 100_000_000:
                raise ValueError("Office/archive decompression limit exceeded; original retained")
            office = any(m.filename in ("[Content_Types].xml", "mimetype") for m in members)
            if not office:
                result.status, result.flags = "unreadable", ["archive_requires_manual_extraction"]
                return result
            texts = []
            for member in members:
                name = member.filename
                if name.endswith(".rels"):
                    root = ElementTree.fromstring(archive.read(member))
                    for relation in root:
                        if relation.get("TargetMode") == "External":
                            add_link(result, relation.get("Target", ""), name, url)
                elif name.endswith(".xml") and name.startswith(("word/", "xl/", "ppt/", "content.xml")):
                    root = ElementTree.fromstring(archive.read(member))
                    texts.append("["+name+"]\n"+"\n".join(t.strip() for t in root.itertext() if t.strip()))
            result.text = "\n\n".join(texts)
            # XML retains values and notes, but diagrams, ordering and formula recalculation require review.
            result.status, result.flags = "partial_text", ["office_layout_and_embedded_objects_need_review"]
    elif "html" in media_type or b"<html" in body[:2000].lower() or b"<!doctype html" in body[:200].lower():
        soup = BeautifulSoup(body, "html.parser")
        result.title = soup.title.get_text(" ", strip=True)[:1000] if soup.title else ""
        root = soup.select_one("main, article, #main-content, #content") or soup.body or soup
        result.text = html_part(str(root), result, url)
        if len(result.text.strip()) < 120 or re.search(r"just a moment|access denied|verify you are human|page not found|sivua ei löytynyt|sidan hittades inte|403 forbidden", result.title, re.I):
            result.status, result.flags = "unreadable", ["javascript_shell_or_access_challenge"]
    elif media_type == "image/png" or body.startswith(b"\x89PNG\r\n\x1a\n"):
        from funding.ocr import read_png
        result.text, result.flags = read_png(body)
        result.status = "partial_text" if result.text else "unreadable"
        result.page_count = 1
    elif "xml" in media_type:
        root = ElementTree.fromstring(body)
        result.text = "\n".join(t.strip() for t in root.itertext() if t.strip())
        for node in root.iter():
            for key, value in node.attrib.items():
                if key.rsplit("}", 1)[-1] in ("href", "url"):
                    add_link(result, value, node.text or "XML reference", url)
    elif media_type.startswith("text/"):
        result.text = body.decode("utf-8", errors="replace")
        if "\ufffd" in result.text:
            result.status, result.flags = "partial_text", ["encoding_needs_review"]
    else:
        result.status, result.flags = "unreadable", ["unsupported_format_original_retained"]
    if not result.text.strip() and result.status == "extracted":
        result.status, result.flags = "unreadable", ["empty_text"]
    if "\ufffd" in result.text:
        result.flags.append("decoding_replacement_characters")
        if result.status == "extracted":
            result.status = "partial_text"
    # One destination per source version; prefer a mandatory/documentary link over a generic link.
    unique = {}
    for link in result.links:
        if link.url not in unique or link.follow:
            unique[link.url] = link
    result.links = list(unique.values())
    return result
