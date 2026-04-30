import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/backup", tags=["backup"])

DATABASES = ("aware_android", "aware_ios")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_USER = os.environ.get("MYSQL_BACKUP_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "")
BACKUP_TMP = Path(os.environ.get("BACKUP_TMP", "/tmp/aware-backups"))
MAX_IMPORT_BYTES = 1024 * 1024 * 1024


def _mysql_env() -> dict[str, str]:
    if not MYSQL_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MYSQL_ROOT_PASSWORD is not configured for backup operations",
        )
    env = os.environ.copy()
    env["MYSQL_PWD"] = MYSQL_PASSWORD
    return env


def _mysql_base_command(binary: str) -> list[str]:
    return [
        binary,
        f"--host={MYSQL_HOST}",
        f"--port={MYSQL_PORT}",
        f"--user={MYSQL_USER}",
    ]


@router.post("/export")
async def export_backup():
    BACKUP_TMP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_path = BACKUP_TMP / f"aware-db-{stamp}.sql.gz"

    dump_command = [
        *_mysql_base_command("mysqldump"),
        "--single-transaction",
        "--routines",
        "--triggers",
        "--databases",
        *DATABASES,
    ]

    with output_path.open("wb") as output:
        dump = subprocess.Popen(
            dump_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_mysql_env(),
        )
        gzip = subprocess.Popen(["gzip", "-c"], stdin=dump.stdout, stdout=output)
        if dump.stdout:
            dump.stdout.close()
        _, dump_err = dump.communicate()
        gzip.wait()

    if dump.returncode != 0 or gzip.returncode != 0:
        output_path.unlink(missing_ok=True)
        message = dump_err.decode("utf-8", errors="replace").strip()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message or "Database export failed",
        )

    return FileResponse(
        output_path,
        media_type="application/gzip",
        filename=output_path.name,
    )


@router.post("/import")
async def import_backup(
    backup: UploadFile = File(...),
):
    if backup.size and backup.size > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Backup file is too large",
        )

    with tempfile.TemporaryDirectory(prefix="aware-restore-") as tmp:
        archive_path = Path(tmp) / "restore.sql.gz"
        with archive_path.open("wb") as target:
            shutil.copyfileobj(backup.file, target)

        if archive_path.stat().st_size > MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Backup file is too large",
            )

        gzip_proc = subprocess.Popen(
            ["gzip", "-dc", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        mysql_proc = subprocess.Popen(
            _mysql_base_command("mysql"),
            stdin=gzip_proc.stdout,
            stderr=subprocess.PIPE,
            env=_mysql_env(),
        )
        if gzip_proc.stdout:
            gzip_proc.stdout.close()
        _, gzip_err = gzip_proc.communicate()
        _, mysql_err = mysql_proc.communicate()

        if gzip_proc.returncode != 0:
            message = gzip_err.decode("utf-8", errors="replace").strip()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message or "Could not read compressed backup",
            )
        if mysql_proc.returncode != 0:
            message = mysql_err.decode("utf-8", errors="replace").strip()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message or "Database import failed",
            )

    return {"success": True}
