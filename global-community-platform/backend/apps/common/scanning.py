"""Malware checks for uploaded documents (PDF, DOC, DOCX, TXT).

Photos are decoded and re-encoded and videos are re-encoded by ffmpeg, so their
original bytes are never served. Documents are served as uploaded, so they get:

1. Built-in checks that always run (no service needed):
   - the bytes must really be the claimed type (a renamed .exe is rejected);
   - the EICAR anti-virus test file is rejected (lets you test the scanner);
   - PDFs with active content are rejected: JavaScript, launch actions, embedded
     files, XFA forms, rich media. Names are decoded (/J#61vaScript) and
     compressed streams are inflated before searching, so hiding them doesn't work;
   - Word files with macros are rejected (vbaProject.bin in DOCX, VBA storage in
     DOC), as are DOCX "zip bombs" and external template links;
   - text files must be text (no NUL bytes, valid UTF-8 or Latin-1).
2. ClamAV, when CLAMD_HOST or CLAMD_SOCKET points at a clamd daemon (INSTREAM).
   If clamd is set up but unreachable, uploads are refused unless CLAMD_FAIL_OPEN.
"""

import io
import logging
import re
import socket
import struct
import zipfile
import zlib

from django.conf import settings

logger = logging.getLogger(__name__)

MAX_SCAN_BYTES = 25 * 1024 * 1024
MAX_INFLATED_BYTES = 64 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

PDF_DANGEROUS_NAMES = {b"/javascript", b"/js", b"/launch", b"/embeddedfile", b"/embeddedfiles",
                       b"/richmedia", b"/xfa", b"/importdata", b"/submitform", b"/gotoe"}


class UnsafeFile(Exception):
    """The upload looks dangerous; the message is safe to show to the user."""


def scan_document(data, extension):
    """Raise UnsafeFile if `data` (bytes) isn't a safe document of `extension`."""
    extension = extension.lower().lstrip(".")
    if len(data) > MAX_SCAN_BYTES:
        raise UnsafeFile("This file is too large to check.")
    if EICAR in data:
        raise UnsafeFile("This file was flagged as malware (EICAR test file).")
    if extension == "pdf":
        _check_pdf(data)
    elif extension == "docx":
        _check_docx(data)
    elif extension == "doc":
        _check_doc(data)
    elif extension == "txt":
        _check_text(data)
    _clamav(data)


def _check_text(data):
    if b"\x00" in data:
        raise UnsafeFile("This doesn't look like a text file.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        # Latin-1 decodes anything; just reject control characters typical of binaries.
        if sum(1 for byte in data[:4096] if byte < 9 or 13 < byte < 32) > 8:
            raise UnsafeFile("This doesn't look like a text file.")


_NAME = re.compile(rb"/[^\s/<>\[\]()%{}]+")
_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)


def _pdf_names(chunk):
    for match in _NAME.finditer(chunk):
        name = _HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), match.group(0))
        yield name.lower()


def _check_pdf(data):
    if not data[:1024].lstrip().startswith(b"%PDF-") and b"%PDF-" not in data[:1024]:
        raise UnsafeFile("This file isn't a real PDF.")
    chunks = [data]
    inflated_total = 0
    for match in _STREAM.finditer(data):
        raw = match.group(1)
        try:
            inflater = zlib.decompressobj()
            inflated = inflater.decompress(raw, MAX_INFLATED_BYTES - inflated_total)
        except zlib.error:
            continue
        inflated_total += len(inflated)
        chunks.append(inflated)
        if inflated_total >= MAX_INFLATED_BYTES:
            raise UnsafeFile("This PDF is too complex to check.")
    for chunk in chunks:
        found = PDF_DANGEROUS_NAMES.intersection(_pdf_names(chunk))
        if found:
            raise UnsafeFile("PDFs with scripts, attachments or interactive forms can't be uploaded. Save it as a plain PDF (\"Print to PDF\") and try again.")
        if b"/aa" in chunk.lower() and re.search(rb"/AA\s*<<", chunk):
            raise UnsafeFile("PDFs with automatic actions can't be uploaded. Save it as a plain PDF and try again.")


def _check_docx(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError):
        raise UnsafeFile("This file isn't a real Word document.")
    names = {info.filename.lower() for info in infos}
    if "word/document.xml" not in names or "[content_types].xml" not in names:
        raise UnsafeFile("This file isn't a real Word document.")
    if sum(info.file_size for info in infos) > MAX_DOCX_UNCOMPRESSED or len(infos) > 2000:
        raise UnsafeFile("This document is too large to check.")
    if any(name.endswith("vbaproject.bin") or name.endswith(".bin") and "activex" in name for name in names):
        raise UnsafeFile("Word documents with macros can't be uploaded. Save it as a normal .docx and try again.")
    if any(name.startswith("word/embeddings/") for name in names):
        raise UnsafeFile("Word documents with embedded files or programs can't be uploaded.")
    for info in infos:
        if info.filename.lower().endswith(".rels"):
            rels = archive.read(info.filename)[:1_000_000].lower()
            # Remote templates / OLE links are how many document exploits fetch payloads.
            if b'targetmode="external"' in rels and (b"attachedtemplate" in rels or b"oleobject" in rels or b"frame" in rels):
                raise UnsafeFile("Word documents that load content from the internet can't be uploaded.")
    content_types = archive.read("[Content_Types].xml")[:1_000_000].lower() if "[Content_Types].xml" in archive.namelist() else b""
    if b"macroenabled" in content_types or b"vbaproject" in content_types:
        raise UnsafeFile("Word documents with macros can't be uploaded. Save it as a normal .docx and try again.")


OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _check_doc(data):
    if not data.startswith(OLE_SIGNATURE):
        raise UnsafeFile("This file isn't a real Word document.")
    # OLE directory entries store stream names in UTF-16LE.
    for marker in ("_VBA_PROJECT", "VBA", "Macros", "ObjectPool", "Ole10Native"):
        if marker.encode("utf-16-le") in data:
            raise UnsafeFile("Old .doc files with macros or embedded objects can't be uploaded. Save it as .docx or PDF and try again.")


def clamav_configured():
    return bool(getattr(settings, "CLAMD_SOCKET", "") or getattr(settings, "CLAMD_HOST", ""))


def _clamav(data):
    if not clamav_configured():
        return
    try:
        result = clamd_instream(data)
    except OSError:
        logger.exception("ClamAV is configured but unreachable")
        if getattr(settings, "CLAMD_FAIL_OPEN", False):
            return
        raise UnsafeFile("We couldn't check this file for viruses right now. Please try again in a few minutes.")
    if result.endswith("FOUND"):
        logger.warning("ClamAV rejected an upload: %s", result)
        raise UnsafeFile("This file was flagged as malware and can't be uploaded.")


def clamd_instream(data, timeout=30):
    """Send `data` to clamd with the INSTREAM command; returns its reply, e.g. 'stream: OK'."""
    if settings.CLAMD_SOCKET:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        address = settings.CLAMD_SOCKET
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        address = (settings.CLAMD_HOST, int(settings.CLAMD_PORT))
    sock.settimeout(timeout)
    with sock:
        sock.connect(address)
        sock.sendall(b"zINSTREAM\0")
        view = memoryview(data)
        for start in range(0, len(data), 64 * 1024):
            chunk = view[start:start + 64 * 1024]
            sock.sendall(struct.pack("!L", len(chunk)) + chunk)
        sock.sendall(struct.pack("!L", 0))
        reply = b""
        while not reply.endswith(b"\0"):
            part = sock.recv(4096)
            if not part:
                break
            reply += part
    return reply.rstrip(b"\0").decode(errors="replace").strip()
