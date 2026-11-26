"""
AWS S3 storage provider implementation.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, BinaryIO, Optional

from src.logger.logger import Logger
from src.services.files.base import SignedUrlResult, StorageProvider, UploadResult


class S3StorageProvider(StorageProvider):
    """AWS S3 storage provider using aioboto3."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize S3 storage provider.

        Args:
            bucket: S3 bucket name
            region: AWS region
            access_key_id: AWS access key (uses env/IAM if not provided)
            secret_access_key: AWS secret key (uses env/IAM if not provided)
            endpoint_url: Custom endpoint URL (for S3-compatible services)
            enabled: Whether S3 storage is enabled
        """
        self.bucket = bucket
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self.enabled = enabled

    @property
    def provider_name(self) -> str:
        return "s3"

    def is_available(self) -> bool:
        """
        Check if S3 storage is available and enabled.

        Returns:
            True if S3 is enabled and configured, False otherwise
        """
        return self.enabled and bool(self.bucket)

    def _get_session_config(self) -> dict[str, Any]:
        """Get aioboto3 session configuration."""
        config = {
            "region_name": self.region,
        }
        if self.access_key_id and self.secret_access_key:
            config["aws_access_key_id"] = self.access_key_id
            config["aws_secret_access_key"] = self.secret_access_key
        return config

    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UploadResult:
        """Upload a file to S3."""
        if not self.is_available():
            Logger.error("S3 storage is not enabled or configured")
            return UploadResult(
                success=False,
                storage_key=storage_key,
                bucket=self.bucket,
                error_message="S3 storage is not enabled or configured",
            )

        try:
            import aioboto3

            session = aioboto3.Session(**self._get_session_config())

            extra_args: dict[str, Any] = {"ContentType": content_type}
            if metadata:
                extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.upload_fileobj(
                    file_data, self.bucket, storage_key, ExtraArgs=extra_args
                )

            Logger.info(f"Uploaded file to s3://{self.bucket}/{storage_key}")
            return UploadResult(
                success=True, storage_key=storage_key, bucket=self.bucket
            )

        except Exception as e:
            Logger.error(f"Failed to upload file to S3: {e}")
            return UploadResult(
                success=False,
                storage_key=storage_key,
                bucket=self.bucket,
                error_message=str(e),
            )

    async def delete(self, storage_key: str) -> bool:
        """Delete a file from S3."""
        try:
            import aioboto3

            session = aioboto3.Session(**self._get_session_config())

            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.delete_object(Bucket=self.bucket, Key=storage_key)

            Logger.info(f"Deleted file from s3://{self.bucket}/{storage_key}")
            return True

        except Exception as e:
            Logger.error(f"Failed to delete file from S3: {e}")
            return False

    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in S3."""
        try:
            import aioboto3

            session = aioboto3.Session(**self._get_session_config())

            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.head_object(Bucket=self.bucket, Key=storage_key)
            return True

        except Exception:
            return False

    async def generate_download_url(
        self, storage_key: str, expires_in: int = 3600, filename: Optional[str] = None
    ) -> SignedUrlResult:
        """Generate a presigned URL for downloading a file."""
        import aioboto3
        from botocore.config import Config

        session = aioboto3.Session(**self._get_session_config())

        params = {"Bucket": self.bucket, "Key": storage_key}

        if filename:
            # Set Content-Disposition for download filename
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=Config(signature_version="s3v4"),
        ) as s3:
            url = await s3.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return SignedUrlResult(url=url, expires_at=expires_at, method="GET")

    async def generate_upload_url(
        self, storage_key: str, content_type: str, expires_in: int = 3600
    ) -> SignedUrlResult:
        """Generate a presigned URL for uploading a file directly to S3."""
        import aioboto3
        from botocore.config import Config

        session = aioboto3.Session(**self._get_session_config())

        params = {
            "Bucket": self.bucket,
            "Key": storage_key,
            "ContentType": content_type,
        }

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=Config(signature_version="s3v4"),
        ) as s3:
            url = await s3.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expires_in
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return SignedUrlResult(url=url, expires_at=expires_at, method="PUT")

    async def get_file_size(self, storage_key: str) -> Optional[int]:
        """Get the size of a file in S3."""
        try:
            import aioboto3

            session = aioboto3.Session(**self._get_session_config())

            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                response = await s3.head_object(Bucket=self.bucket, Key=storage_key)
                return response.get("ContentLength")

        except Exception:
            return None

    async def download_bytes(
        self, storage_key: str, max_bytes: Optional[int] = None
    ) -> Optional[bytes]:
        """
        Download file content as bytes from S3.

        Args:
            storage_key: The key/path of the file
            max_bytes: Maximum number of bytes to download (None for all)

        Returns:
            File content as bytes, or None if file doesn't exist
        """
        try:
            import aioboto3

            session = aioboto3.Session(**self._get_session_config())

            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                params: dict[str, Any] = {"Bucket": self.bucket, "Key": storage_key}

                # Use Range header to limit bytes downloaded
                if max_bytes is not None:
                    params["Range"] = f"bytes=0-{max_bytes - 1}"

                response = await s3.get_object(**params)

                # Read the body
                async with response["Body"] as stream:
                    data = await stream.read()

                return data

        except Exception as e:
            Logger.error(f"Failed to download file from S3: {e}")
            return None


# Default S3 storage instance (configured at startup)
s3_storage: Optional[S3StorageProvider] = None


def init_s3_storage(
    bucket: str,
    region: str = "us-east-1",
    access_key_id: Optional[str] = None,
    secret_access_key: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    enabled: bool = True,
) -> S3StorageProvider:
    """Initialize the global S3 storage provider."""
    global s3_storage
    s3_storage = S3StorageProvider(
        bucket=bucket,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        endpoint_url=endpoint_url,
        enabled=enabled,
    )
    return s3_storage


def is_s3_available() -> bool:
    """
    Check if S3 storage is available.

    Returns:
        True if S3 storage is configured and enabled, False otherwise
    """
    return s3_storage is not None and s3_storage.is_available()
