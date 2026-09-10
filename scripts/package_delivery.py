"""Bundle the portable project, source data and human-readable delivery together."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--compact", action="store_true", help="Keep originals in the database and omit duplicate standalone originals")
args = parser.parse_args()
root = Path.cwd()
out = root/("outputs/rahoitusrekisteri-azure.zip" if args.compact else "outputs/rahoitusrekisteri-microsoft.zip")
staged = out.with_suffix(".zip.part")
files = []
for name in ["README.md", "pyproject.toml", "uv.lock", "requirements.lock", "Dockerfile", "compose.yaml", "azure-pipelines.yml", "alembic.ini", ".env.example", ".dockerignore", ".gitignore"]:
    files.append((root/name, name))
for folder in ["src", "config", "migrations", "infra", "integrations", "docs", "tests", "scripts"]:
    for path in sorted((root/folder).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            files.append((path, str(path.relative_to(root))))
for path in sorted((root/"outputs/data").iterdir()):
    if path.suffix in {".db", ".csv", ".jsonl", ".json"}:
        files.append((path, f"data/{path.name}"))
for path in sorted((root/"outputs/data/documents").rglob("*")):
    if path.is_file():
        files.append((path, "data/documents/"+str(path.relative_to(root/"outputs/data/documents"))))
files.append((root/"outputs/rahoitusrekisteri.xlsx", "rahoitusrekisteri.xlsx"))
originals = {}
if args.compact:
    included = []
    for path, name in files:
        if name.startswith("data/documents/originals/"):
            with path.open("rb") as stream:
                originals[name] = {"bytes": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
        else:
            included.append((path, name))
    files = included
manifest = {}
print(json.dumps({"stage": "starting", "files": len(files)}), flush=True)
with ZipFile(staged, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
    for index, (path, name) in enumerate(files, 1):
        if path.stat().st_size >= 100_000_000:
            print(json.dumps({"stage": "compressing_large_file", "file": name, "bytes": path.stat().st_size}), flush=True)
        archive.write(path, name)
        with path.open("rb") as stream:
            manifest[name] = {"bytes": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
        if index % 5000 == 0:
            print(json.dumps({"stage": "compressing", "files": index, "total_files": len(files)}), flush=True)
    expected_database_sha = json.loads((root/"outputs/data/metrics.json").read_text())["database_sha256"]
    assert manifest["data/funding.db"]["sha256"] == expected_database_sha, "Database changed after snapshot validation"
    if args.compact:
        original_manifest = (json.dumps(originals, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
        archive.writestr("ORIGINALS-MANIFEST.json", original_manifest)
        manifest["ORIGINALS-MANIFEST.json"] = {"bytes": len(original_manifest), "sha256": hashlib.sha256(original_manifest).hexdigest()}
    archive.writestr("FILE-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
print(json.dumps({"stage": "checking_zip_integrity", "files": len(files)}), flush=True)
with ZipFile(staged) as archive:
    assert archive.testzip() is None
with staged.open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
staged.replace(out)
out.with_suffix(".sha256").write_text(f"{checksum}  {out.name}\n")
print(json.dumps({"zip": str(out), "files": len(files), "bytes": out.stat().st_size,
                  "payload_bytes": sum(item["bytes"] for item in manifest.values()),
                  "sha256": checksum, "zip_integrity": "passed"}))
