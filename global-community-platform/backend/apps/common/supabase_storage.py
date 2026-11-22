"""Django storage backend for Supabase Storage (its REST API).

Used when the Supabase integration provides SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY (e.g. the Vercel Marketplace integration), so no
separate S3 access keys are needed. Files live in one private bucket; browsers
get short-lived signed URLs (which support HTTP Range, so videos can seek).
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


class SupabaseStorageError(Exception):
    pass


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self, url=None, key=None, bucket=None, expires=None, timeout=60):
        self.base = (url or settings.SUPABASE_URL).rstrip("/") + "/storage/v1"
        self.key = key or settings.SUPABASE_SERVICE_ROLE_KEY
        self.bucket = bucket or settings.SUPABASE_STORAGE_BUCKET
        self.expires = int(expires or settings.SUPABASE_URL_EXPIRE)
        self.timeout = timeout

    # ------------------------------------------------------------ HTTP
    def _path(self, name):
        return urllib.parse.quote(name.lstrip("/"), safe="/")

    def _request(self, method, path, body=None, headers=None):
        """Return (status, headers, body bytes). 4xx/5xx raise unless 404/400 on reads."""
        request = urllib.request.Request(self.base + path, data=body, method=method)
        request.add_header("Authorization", f"Bearer {self.key}")
        request.add_header("apikey", self.key)
        for header, value in (headers or {}).items():
            request.add_header(header, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), error.read()

    def _ensure(self, status, body, action, name):
        if status >= 300:
            raise SupabaseStorageError(f"{action} {name!r} failed: HTTP {status} {body[:200]!r}")

    # ------------------------------------------------------------ Storage API
    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        data = content.read()
        if isinstance(data, str):
            data = data.encode()
        content_type = getattr(content, "content_type", None) or "application/octet-stream"
        status, _, body = self._request(
            "POST", f"/object/{self.bucket}/{self._path(name)}", data,
            {"Content-Type": content_type, "x-upsert": "false", "Cache-Control": "max-age=31536000"},
        )
        self._ensure(status, body, "Upload", name)
        return name

    def _open(self, name, mode="rb"):
        status, _, body = self._request("GET", f"/object/{self.bucket}/{self._path(name)}")
        if status == 404 or status == 400:
            raise FileNotFoundError(name)
        self._ensure(status, body, "Download", name)
        return ContentFile(body, name=name)

    def delete(self, name):
        if not name:
            return
        status, _, body = self._request(
            "DELETE", f"/object/{self.bucket}", json.dumps({"prefixes": [name]}).encode(),
            {"Content-Type": "application/json"},
        )
        if status not in (200, 204, 404):
            self._ensure(status, body, "Delete", name)

    def _info(self, name):
        status, headers, body = self._request("GET", f"/object/info/{self.bucket}/{self._path(name)}")
        if status in (400, 404):
            return None
        self._ensure(status, body, "Info", name)
        try:
            return json.loads(body or b"{}")
        except ValueError:
            return {}

    def exists(self, name):
        return self._info(name) is not None

    def size(self, name):
        info = self._info(name)
        if info is None:
            raise FileNotFoundError(name)
        metadata = info.get("metadata") or {}
        return int(info.get("size") or metadata.get("size") or metadata.get("contentLength") or 0)

    def url(self, name):
        status, _, body = self._request(
            "POST", f"/object/sign/{self.bucket}/{self._path(name)}",
            json.dumps({"expiresIn": self.expires}).encode(), {"Content-Type": "application/json"},
        )
        self._ensure(status, body, "Sign", name)
        signed = json.loads(body).get("signedURL") or json.loads(body).get("signedUrl")
        return self.base + signed if signed.startswith("/") else signed

    def check(self):
        """Cheap health probe: can we see the bucket?"""
        status, _, _ = self._request("GET", f"/bucket/{self.bucket}")
        return status == 200
