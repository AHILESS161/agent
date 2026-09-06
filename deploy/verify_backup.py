"""Compare every restored DB document reference with the archived blob hash."""
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import PurePosixPath

container, archive = sys.argv[1:]
query = "SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT stored_path,sha256 FROM source_documents) t"
result = subprocess.run(["docker", "exec", container, "psql", "-U", "postgres", "-At", "-c", query],
                        capture_output=True, text=True, check=True)
references = json.loads(result.stdout)
with tarfile.open(archive, "r:gz") as bundle:
    for row in references:
        path = PurePosixPath(row["stored_path"])
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Unsafe document reference")
        member = bundle.getmember("./" + path.as_posix())
        if not member.isfile():
            raise RuntimeError("Document blob is not a regular file")
        with bundle.extractfile(member) as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != row["sha256"]:
            raise RuntimeError("Restored document checksum mismatch")
print(f"PASS: restored DB and {len(references)} document references verified")
