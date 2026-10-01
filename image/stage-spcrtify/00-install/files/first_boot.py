"""Import an optional local Spotify seed, then remove it from the boot partition."""
import json
import os
from pathlib import Path
import pwd


def import_spotify(boot, data, uid, gid):
    seed = boot / "spcrtify-spotify.json"
    if not seed.exists():
        return
    tokens = json.loads(seed.read_text())
    if not all(isinstance(tokens.get(key), str) and tokens[key] for key in ("client_id", "refresh_token")):
        raise ValueError("Invalid Spotify seed; leaving it for correction")
    temporary = data / "spotify.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    os.fchown(fd, uid, gid)
    with os.fdopen(fd, "w") as stream:
        json.dump(tokens, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(data / "spotify.json")
    directory = os.open(data, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    seed.unlink()


if __name__ == "__main__":
    user = pwd.getpwnam("spcrtify")
    import_spotify(Path("/boot/firmware"), Path("/var/lib/spcrtify"), user.pw_uid, user.pw_gid)
