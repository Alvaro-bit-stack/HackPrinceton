"""Family profile (child and family members), one JSON file for the single demo family. Git-ignored."""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

PATH = Path(__file__).parent / "data" / "family.json"
_lock = threading.Lock()
_ID = re.compile(r"^[a-z0-9-]{1,30}$")


def _empty():
    return {"child_name": None, "child_age_months": None, "members": []}


def load_family(path=PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return clean_family(data)
    except (OSError, ValueError, TypeError, AttributeError):
        return _empty()


def clean_family(profile):
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    name = profile.get("child_name")
    if name is not None:
        if not isinstance(name, str):
            raise ValueError("child_name must be text")
        name = name.strip() or None
        if name and len(name) > 60:
            raise ValueError("child_name must be at most 60 characters")
    age = profile.get("child_age_months")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 216):
        raise ValueError("child_age_months must be a whole number from 0 to 216")
    members = profile.get("members") or []
    if not isinstance(members, list) or len(members) > 8:
        raise ValueError("at most 8 family members")
    out, seen = [], set()
    for m in members:
        if not isinstance(m, dict):
            raise ValueError("each member must be an object")
        mid, mname, avatar = m.get("id"), m.get("name"), m.get("avatar")
        if not isinstance(mid, str) or not _ID.match(mid) or mid in seen:
            raise ValueError("member id must be 1 to 30 characters of a-z, 0-9, - and unique")
        seen.add(mid)
        mname = mname.strip() if isinstance(mname, str) else ""
        if not mname or len(mname) > 40:
            raise ValueError("member name must be 1 to 40 characters")
        if avatar is not None:
            if not isinstance(avatar, str) or len(avatar.strip()) > 40:
                raise ValueError("avatar must be text of at most 40 characters")
            avatar = avatar.strip() or None
        out.append({"id": mid, "name": mname, "avatar": avatar})
    return {"child_name": name, "child_age_months": age, "members": out}


def save_family(profile, path=PATH):
    cleaned = clean_family(profile)
    path = Path(path)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
        os.replace(tmp, path)  # readers never see a half-written file
    return cleaned
