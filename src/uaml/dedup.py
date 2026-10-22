"""Conservative exact identity and Unicode lexical candidates, never merging."""
import re
import unicodedata

from .formats import digest, json_bytes


def applicability(header):
    app = header["applicability"]
    return {"os": sorted(v.casefold() for v in app["os"]),
            "architecture": sorted(v.casefold() for v in app["architecture"]),
            "components": sorted((c["name"].casefold(), c["version"]) for c in app["components"]),
            "conditions": sorted(app.get("conditions", []))}


def exact_key(header, body):
    # Dates and source-project IDs are provenance, not permission to create a
    # second authority. Return the existing note; never discard or merge evidence.
    value = {"title": header["title"], "category": header["category"],
             "body": body.replace("\r\n", "\n"), "applicability": applicability(header),
             "status": header["status"], "evidence": header["verification"]["evidence"],
             "related_ids": sorted(header["related_ids"]), "supersedes": sorted(header["supersedes"]),
             "deprecation_reason": header.get("deprecation_reason"), "superseded_by": header.get("superseded_by"),
             "supersession_reason": header.get("supersession_reason")}
    return digest(json_bytes(value))


def tokens(text):
    words = re.findall(r"\w+(?:[.+/-]\w+)*", unicodedata.normalize("NFKC", text).casefold())
    result = set()
    for word in words:
        result.add("w:" + word)
        if any("\u3400" <= c <= "\u9fff" for c in word):
            result.update("c:" + word[i:i + 2] for i in range(max(0, len(word) - 1)))
    return result


def jaccard(a, b):
    return len(a & b) / len(a | b) if a or b else 0.0


def catalog_hash(notes):
    return digest(json_bytes({"notes": sorted((note["metadata"]["id"], note["sha256"]) for note in notes)}))


def candidates(header, body, notes):
    exact, similar = [], []
    key = exact_key(header, body)
    for note in notes:
        other = note["metadata"]
        if other["id"] == header["id"] or applicability(other) != applicability(header):
            continue
        if key == exact_key(other, note["body"]):
            exact.append({"id": other["id"], "sha256": note["sha256"]})
            continue
        score = (0.4 * jaccard(tokens(header["title"]), tokens(other["title"])) +
                 0.6 * jaccard(tokens(body), tokens(note["body"])))
        if score >= 0.65:
            similar.append({"id": other["id"], "sha256": note["sha256"], "score": round(score, 4),
                            "reason": "Similar Unicode text in the same environment; review semantic differences, negation and versions."})
    return {"exact": sorted(exact, key=lambda item: item["id"]),
            "similar": sorted(similar, key=lambda item: (-item["score"], item["id"]))}
