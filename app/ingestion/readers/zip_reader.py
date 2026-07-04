"""
ZipReader — extracts a supported file from a ZIP archive and delegates to the
correct reader.

A ZIP archive is not a dataset format — it is a container. This reader:
1. Opens the ZIP and inspects its contents
2. Finds the first supported file (CSV or Excel) inside
3. Extracts that file to a temp directory
4. Delegates to CSVReader or ExcelReader as appropriate
5. Returns the same (DataFrame, DatasetSchema) contract as all other readers

Design decisions:
- Only single-file ZIP archives are supported in this version
- Multi-file ZIPs raise FileReadException (ambiguous intent)
- Password-protected ZIPs raise FileReadException
- The extracted temp file is cleaned up after reading

Future: Accept a filename hint to select a specific file from a multi-file ZIP.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Generator

import pandas as pd

from app.core.exceptions import FileReadException, InvalidFileTypeException
from app.ingestion.models import DatasetSchema
from app.ingestion.readers.base_reader import BaseReader
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Extensions inside the ZIP that can be ingested
SUPPORTED_INNER_EXTENSIONS = frozenset({"csv", "xlsx", "xls"})


class ZipReader(BaseReader):
    """
    Reads a supported dataset file from inside a ZIP archive.

    The ZIP must contain exactly one supported file.
    """

    @property
    def reader_name(self) -> str:
        return "ZipReader"

    def can_read(self, file_extension: str) -> bool:
        return file_extension.lower() == "zip"

    def read(
        self,
        file_path: Path,
        **kwargs: object,
    ) -> tuple[pd.DataFrame, DatasetSchema]:
        """
        Extract the inner file and read it with the appropriate reader.

        Args:
            file_path: Path to the ZIP archive.
            **kwargs:  Passed through to the inner reader (encoding, delimiter, etc.)

        Returns:
            (DataFrame, DatasetSchema) from the inner file.

        Raises:
            FileReadException:        Archive is corrupt, password-protected, or
                                      contains no/multiple supported files.
            InvalidFileTypeException: Inner file extension is not supported.
        """
        inner_path, tmp_dir = self._extract_inner_file(file_path)
        try:
            from app.ingestion.readers.reader_factory import ReaderFactory
            ext = inner_path.suffix.lstrip(".").lower()
            reader = ReaderFactory.get_reader(ext)
            df, schema = reader.read(inner_path, **kwargs)
            logger.info(
                "ZIP file read",
                archive=file_path.name,
                inner_file=inner_path.name,
                rows=len(df),
            )
            return df, schema
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def read_chunked(
        self,
        file_path: Path,
        chunk_size: int = 10_000,
        **kwargs: object,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract the inner file and read it in chunks.

        Yields:
            DataFrames of up to chunk_size rows.
        """
        inner_path, tmp_dir = self._extract_inner_file(file_path)
        try:
            from app.ingestion.readers.reader_factory import ReaderFactory
            ext = inner_path.suffix.lstrip(".").lower()
            reader = ReaderFactory.get_reader(ext)
            yield from reader.read_chunked(inner_path, chunk_size=chunk_size, **kwargs)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def list_contents(self, file_path: Path) -> list[str]:
        """
        Return the names of all files inside a ZIP archive.

        Args:
            file_path: Path to the ZIP file.

        Returns:
            List of filenames inside the archive.
        """
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                return [info.filename for info in zf.infolist() if not info.is_dir()]
        except zipfile.BadZipFile as exc:
            raise FileReadException(
                message=f"Cannot read ZIP archive '{file_path.name}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_inner_file(self, zip_path: Path) -> tuple[Path, Path]:
        """
        Open the ZIP and extract the single supported inner file to a temp dir.

        Returns:
            (inner_file_path, temp_directory_path)
            The caller is responsible for cleaning up the temp directory.

        Raises:
            FileReadException: Multiple or zero supported files found,
                               or archive is corrupt / password-protected.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Check for password protection
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # bit 0 = encrypted
                        raise FileReadException(
                            message=(
                                f"ZIP archive '{zip_path.name}' is password-protected. "
                                "Remove the password before uploading."
                            )
                        )

                # Find supported files (skip directories and hidden files)
                candidates = [
                    name for name in zf.namelist()
                    if not name.endswith("/")
                    and not Path(name).name.startswith(".")
                    and Path(name).suffix.lstrip(".").lower() in SUPPORTED_INNER_EXTENSIONS
                ]

                if not candidates:
                    raise FileReadException(
                        message=(
                            f"ZIP archive '{zip_path.name}' contains no supported files "
                            f"(csv, xlsx, xls). Found: {zf.namelist()}"
                        )
                    )

                if len(candidates) > 1:
                    raise FileReadException(
                        message=(
                            f"ZIP archive '{zip_path.name}' contains multiple supported files: "
                            f"{candidates}. "
                            "Upload a single-file ZIP or extract and upload the file directly."
                        )
                    )

                inner_name = candidates[0]
                tmp_dir = Path(tempfile.mkdtemp())
                zf.extract(inner_name, path=str(tmp_dir))
                inner_path = tmp_dir / inner_name

                logger.debug(
                    "ZIP extracted",
                    archive=zip_path.name,
                    inner_file=inner_name,
                    tmp_dir=str(tmp_dir),
                )
                return inner_path, tmp_dir

        except zipfile.BadZipFile as exc:
            raise FileReadException(
                message=f"Corrupt ZIP archive '{zip_path.name}': {exc}"
            ) from exc
        except FileReadException:
            raise
        except Exception as exc:
            raise FileReadException(
                message=f"Cannot process ZIP archive '{zip_path.name}': {exc}"
            ) from exc
