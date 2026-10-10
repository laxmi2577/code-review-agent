import json
import logging
import shutil
from pathlib import Path
from typing import Any

from src.config import Settings, get_settings

logger = logging.getLogger("codelens.storage")


class StorageClient:
    """Manages downloading, uploading, and local caching of vector indices and metadata."""

    def __init__(
        self,
        settings: Settings | None = None,
        base_cache_dir: str | Path | None = None,
    ):
        self.settings = settings or get_settings()
        if base_cache_dir:
            self.base_cache_dir = Path(base_cache_dir)
        else:
            self.base_cache_dir = Path(self.settings.local_index_path).parent

        self.base_cache_dir.mkdir(parents=True, exist_ok=True)
        self.gcs_bucket_name = self.settings.gcs_bucket

    def _sanitize_repo_name(self, repo_name: str) -> str:
        """Sanitize repo name for safe local directory naming."""
        return repo_name.replace("/", "__").replace("\\", "__")

    def get_local_paths(self, repo_name: str) -> tuple[Path, Path]:
        """Return the local paths for index binary and metadata JSON for a repository."""
        safe_name = self._sanitize_repo_name(repo_name)
        repo_dir = self.base_cache_dir / safe_name
        index_path = repo_dir / "faiss_index.bin"
        metadata_path = repo_dir / "metadata.json"
        return index_path, metadata_path

    def index_exists(self, repo_name: str) -> bool:
        """Check whether local index and metadata files exist and are non-empty."""
        index_path, metadata_path = self.get_local_paths(repo_name)
        return (
            index_path.exists()
            and metadata_path.exists()
            and index_path.stat().st_size > 0
            and metadata_path.stat().st_size > 0
        )

    def save_index_data(
        self,
        repo_name: str,
        index_bytes: bytes,
        metadata_dict: dict[str, Any],
    ) -> tuple[Path, Path]:
        """Save raw index bytes and metadata dictionary to the local cache directory."""
        index_path, metadata_path = self.get_local_paths(repo_name)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        with open(index_path, "wb") as f:
            f.write(index_bytes)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2)

        logger.info(
            "Saved vector index and metadata for '%s' to local cache (%s, %s)",
            repo_name,
            index_path,
            metadata_path,
        )
        return index_path, metadata_path

    def load_metadata(self, repo_name: str) -> dict[str, Any] | None:
        """Load and return the metadata dictionary for a repository if present."""
        _, metadata_path = self.get_local_paths(repo_name)
        if not metadata_path.exists():
            return None
        try:
            with open(metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to parse metadata JSON at %s: %s", metadata_path, e)
            return None

    def download_index(
        self,
        repo_name: str,
        force_download: bool = False,
    ) -> tuple[Path | None, Path | None]:
        """Download or retrieve index binary and metadata for a repository.

        Attempts remote GCS download if configured; falls back gracefully to local cache.
        Returns (index_path, metadata_path) if available, or (None, None) if missing.
        """
        index_path, metadata_path = self.get_local_paths(repo_name)

        # Check local cache first unless force_download requested
        if not force_download and self.index_exists(repo_name):
            logger.info("Using cached vector index for '%s' at %s", repo_name, index_path)
            return index_path, metadata_path

        # Attempt remote GCS download if storage SDK is available and configured
        downloaded = self._try_gcs_download(repo_name, index_path, metadata_path)
        if downloaded:
            return index_path, metadata_path

        # Fallback to local cache if present
        if self.index_exists(repo_name):
            logger.info("Remote download not available; using local cache for '%s'", repo_name)
            return index_path, metadata_path

        # Graceful handling of missing index
        logger.warning(
            "Vector index snapshot for repo '%s' was not found in remote storage (gs://%s) or local cache.",
            repo_name,
            self.gcs_bucket_name,
        )
        return None, None

    def upload_index(
        self,
        repo_name: str,
        index_path: str | Path,
        metadata_path: str | Path,
    ) -> bool:
        """Upload index and metadata to local cache and remote storage (if configured)."""
        idx_src = Path(index_path)
        meta_src = Path(metadata_path)

        if not idx_src.exists() or not meta_src.exists():
            logger.error(
                "Cannot upload missing index files: index=%s, metadata=%s",
                idx_src,
                meta_src,
            )
            return False

        # Copy to local cache directory
        target_idx, target_meta = self.get_local_paths(repo_name)
        target_idx.parent.mkdir(parents=True, exist_ok=True)
        if idx_src.resolve() != target_idx.resolve():
            shutil.copy2(idx_src, target_idx)
        if meta_src.resolve() != target_meta.resolve():
            shutil.copy2(meta_src, target_meta)

        # Attempt remote GCS upload
        self._try_gcs_upload(repo_name, target_idx, target_meta)
        return True

    def _try_gcs_download(self, repo_name: str, index_dest: Path, meta_dest: Path) -> bool:
        """Attempt to download index from Google Cloud Storage using GCS client if available."""
        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket_name)

            remote_idx_blob = bucket.blob(f"indices/{repo_name}/faiss_index.bin")
            remote_meta_blob = bucket.blob(f"indices/{repo_name}/metadata.json")

            if not remote_idx_blob.exists() or not remote_meta_blob.exists():
                return False

            index_dest.parent.mkdir(parents=True, exist_ok=True)
            remote_idx_blob.download_to_filename(str(index_dest))
            remote_meta_blob.download_to_filename(str(meta_dest))

            logger.info(
                "Successfully downloaded index from gs://%s/indices/%s/",
                self.gcs_bucket_name,
                repo_name,
            )
            return True
        except ImportError:
            # GCS SDK not installed, standard local fallback
            return False
        except Exception as e:
            logger.warning(
                "Remote GCS download failed for repo '%s' (%s). Falling back to local cache.",
                repo_name,
                e,
            )
            return False

    def _try_gcs_upload(self, repo_name: str, index_src: Path, meta_src: Path) -> bool:
        """Attempt to upload index to Google Cloud Storage using GCS client if available."""
        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket_name)

            remote_idx_blob = bucket.blob(f"indices/{repo_name}/faiss_index.bin")
            remote_meta_blob = bucket.blob(f"indices/{repo_name}/metadata.json")

            remote_idx_blob.upload_from_filename(str(index_src))
            remote_meta_blob.upload_from_filename(str(meta_src))

            logger.info(
                "Successfully uploaded index to gs://%s/indices/%s/",
                self.gcs_bucket_name,
                repo_name,
            )
            return True
        except ImportError:
            return False
        except Exception as e:
            logger.warning(
                "Remote GCS upload failed for repo '%s' (%s). Local copy retained.",
                repo_name,
                e,
            )
            return False
