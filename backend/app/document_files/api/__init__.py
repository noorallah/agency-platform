"""Transport helpers the bill and receipt routers share for uploaded files.

The routes themselves live in each document's own router, beside that
document's permission scopes; what is here is the part that would otherwise
be written twice -- reading an upload under the size limit, and answering a
download with the right type and file name.
"""

from urllib.parse import quote

from fastapi import Response, UploadFile

from app.core.exceptions import ValidationError
from app.document_files.models import DocumentFile
from app.document_files.services import MAX_FILE_BYTES


async def read_upload(file: UploadFile) -> bytes:
    """Read an upload, refusing one past the limit without holding all of it.

    One byte past the limit is read, so an oversized file is refused by name
    rather than buffered whole.
    """
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError("The file is larger than 10 MB, the most it may be.")
    return content


def download_response(row: DocumentFile, content: bytes) -> Response:
    """Answer a download with the stored type and the file's own name."""
    ascii_name = row.file_name.encode("ascii", "replace").decode().replace('"', "'")
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(row.file_name)}"
    )
    return Response(
        content=content,
        media_type=row.content_type,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["download_response", "read_upload"]
