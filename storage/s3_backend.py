"""
High-Speed S3-Compatible Cloud Storage Backend.
Supports: Cloudflare R2 (Free 10GB/month, zero egress fee), Backblaze B2, MinIO, AWS S3.
Uses pure REST / AWS Signature Version 4 (AWS4-HMAC-SHA256) via standard requests library.
Ultra lightweight, zero heavy dependencies required.
"""
import hmac
import hashlib
import datetime
import urllib.parse
from typing import Dict, Any, Tuple, Optional, Callable
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from storage.base import BaseStorageBackend

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(('AWS4' + key).encode('utf-8'), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, 'aws4_request')
    return k_signing

class S3CompatibleBackend(BaseStorageBackend):
    @property
    def provider_name(self) -> str:
        return "s3_r2"

    @property
    def display_name(self) -> str:
        return "Cloudflare R2 / S3 Cloud (Ultra Fast ⚡)"

    def __init__(
        self,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        region: str = "auto"
    ):
        self.endpoint_url = endpoint_url.strip().rstrip('/')
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.bucket_name = bucket_name.strip()
        self.region = region.strip() or "auto"

        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def is_configured(self) -> bool:
        return bool(self.endpoint_url and self.access_key_id and self.secret_access_key and self.bucket_name)

    def _get_auth_headers(self, method: str, path: str, payload_bytes: bytes = b"", headers_extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Generate AWS Signature Version 4 Authorization headers."""
        t = datetime.datetime.now(datetime.timezone.utc)
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = t.strftime('%Y%m%d')

        parsed_url = urllib.parse.urlparse(self.endpoint_url)
        host = parsed_url.netloc

        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        headers = {
            'host': host,
            'x-amz-date': amz_date,
            'x-amz-content-sha256': payload_hash
        }
        if headers_extra:
            for k, v in headers_extra.items():
                headers[k.lower()] = v

        sorted_headers = sorted(headers.items())
        canonical_headers = "".join([f"{k}:{v}\n" for k, v in sorted_headers])
        signed_headers = ";".join([k for k, _ in sorted_headers])

        canonical_uri = path if path.startswith('/') else '/' + path
        canonical_request = f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

        signing_key = _get_signature_key(self.secret_access_key, date_stamp, self.region, 's3')
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        authorization_header = (
            f"{algorithm} Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        out_headers = dict(headers)
        out_headers['Authorization'] = authorization_header
        return out_headers

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "S3 / Cloudflare R2 credentials are incomplete."
        try:
            path = f"/{self.bucket_name}?max-keys=1"
            headers = self._get_auth_headers("GET", path)
            url = f"{self.endpoint_url}{path}"
            r = self.session.get(url, headers=headers, timeout=10)
            if r.status_code in (200, 204):
                return True, f"Connected to S3/R2 Bucket [{self.bucket_name}] successfully!"
            return False, f"S3 Bucket access error (HTTP {r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, f"S3 Connection failed: {str(e)}"

    def upload_chunk(
        self,
        chunk_data: bytes,
        chunk_name: str,
        caption: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Uploads chunk object to S3 / Cloudflare R2 bucket."""
        object_key = f"cloud_pool/{chunk_name}"
        path = f"/{self.bucket_name}/{urllib.parse.quote(object_key)}"
        extra_headers = {"content-type": "application/octet-stream"}
        headers = self._get_auth_headers("PUT", path, payload_bytes=chunk_data, headers_extra=extra_headers)

        url = f"{self.endpoint_url}{path}"
        r = self.session.put(url, data=chunk_data, headers=headers, timeout=120)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"S3 Upload failed with HTTP {r.status_code}: {r.text[:250]}")

        if progress_callback:
            progress_callback(len(chunk_data), len(chunk_data))

        return {
            "file_id": object_key,
            "file_unique_id": object_key,
            "file_size": len(chunk_data),
            "message_id": 0
        }

    def download_chunk(
        self,
        file_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bytes:
        """Downloads chunk object from S3 / Cloudflare R2 bucket."""
        object_key = file_id
        path = f"/{self.bucket_name}/{urllib.parse.quote(object_key)}"
        headers = self._get_auth_headers("GET", path)
        url = f"{self.endpoint_url}{path}"

        r = self.session.get(url, headers=headers, stream=True, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"S3 Download failed with HTTP {r.status_code}: {r.text[:250]}")

        content_len = int(r.headers.get("content-length", 0))
        chunks = []
        downloaded = 0
        for chunk in r.iter_content(chunk_size=1048576):
            if chunk:
                chunks.append(chunk)
                downloaded += len(chunk)
                if progress_callback and content_len > 0:
                    progress_callback(downloaded, content_len)

        data = b"".join(chunks)
        if progress_callback and content_len == 0:
            progress_callback(len(data), len(data))
        return data

    def delete_chunk(self, file_id: str, message_id: int = 0) -> bool:
        """Deletes chunk object from S3 / Cloudflare R2 bucket."""
        try:
            object_key = file_id
            path = f"/{self.bucket_name}/{urllib.parse.quote(object_key)}"
            headers = self._get_auth_headers("DELETE", path)
            url = f"{self.endpoint_url}{path}"
            r = self.session.delete(url, headers=headers, timeout=15)
            return r.status_code in (200, 204)
        except Exception:
            return False
