import re
from collections import defaultdict

from sqlalchemy import select

from app.db import workspace_lock
from app.errors import DomainError
from app.integrations.x_client import parse_time
from app.models import Candidate, Evidence, Outreach, SearchResult, SearchRun, now
from app.security import digest


def terms_from(value):
    terms = [x.strip() for x in value.split(",") if x.strip()]
    if not terms or len(terms) > 5:
        raise DomainError("INVALID_QUERY", "Enter one to five comma-separated topic terms.", 400)
    if any(not re.fullmatch(r"[\w '\-]{2,40}", term, re.UNICODE) for term in terms):
        raise DomainError("INVALID_QUERY", "Use short words or phrases, without X query operators.", 400)
    return list(dict.fromkeys(terms))


def build_query(topics, roles="", location=""):
    terms = terms_from(topics)
    query = "(" + " OR ".join(f'"{t}"' for t in terms) + ")"
    for optional in [roles, location]:
        if optional.strip():
            query += " (" + " OR ".join(f'"{t}"' for t in terms_from(optional)) + ")"
    query += " -is:retweet lang:en"
    if len(query) > 512:
        raise DomainError("INVALID_QUERY", "This query is too long. Use fewer terms.", 400)
    return query, terms


def score_candidate(profile, posts, terms):
    combined = (profile.get("description", "") + " " + " ".join(p["text"] for p in posts)).lower()
    matches = [t for t in terms if re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", combined)]
    topic = min(4, 2 * len(matches))
    build_posts = [p for p in posts if re.search(
        r"\b(i['’]m (building|researching|developing|testing)|we (built|released|developed)|"
        r"our (lab|research|robotics|benchmark|experiments)|i built)\b", p["text"], re.I)]
    role = bool(re.search(r"\b(researcher|research engineer|founder|developer|engineer)\b",
                          profile.get("description", ""), re.I))
    recent = [p for p in posts if (now() - parse_time(p["created_at"])).total_seconds() < 7 * 86400]
    reasons = [
        {"label": "Topic evidence", "points": topic, "detail": ", ".join(matches) or "No direct match"},
        {"label": "Building or research evidence", "points": 3 if build_posts else 0,
         "detail": build_posts[0]["id"] if build_posts else "No first-person project evidence"},
        {"label": "Public role evidence", "points": 2 if role else 0,
         "detail": profile.get("description", "")[:160] if role else "Role unclear"},
        {"label": "Recent activity", "points": 1 if recent else 0, "detail": "Within seven-day sample"},
    ]
    return sum(x["points"] for x in reasons), reasons


def upsert_candidate(db, profile, manual=False):
    x_id = str(profile["id"])
    row = db.get(Candidate, x_id)
    if row is None:
        row = Candidate(x_id=x_id, handle=profile["username"], name=profile.get("name", profile["username"]),
                        bio=profile.get("description", ""), location=profile.get("location", ""), manual=manual)
        db.add(row)
        db.flush()
    else:
        row.handle, row.name = profile["username"], profile.get("name", profile["username"])
        row.bio, row.location = profile.get("description", ""), profile.get("location", "")
        row.available = not profile.get("protected", False)
    return row


def discover(rt, topics, roles="", location="", exclude=(), seed=None):
    """exclude: X ids to leave out (seed accounts). seed: {"handles", "summary"} kept on the run."""
    query, terms = build_query(topics, roles, location)
    payload = rt.read("search", query)
    posts = payload.get("data") or []
    by_author = defaultdict(list)
    for post in posts[:50]:
        if all(k in post for k in ("id", "author_id", "text", "created_at")):
            by_author[str(post["author_id"])].append(post)
    sender = rt.active_account().x_id
    ranked = []
    for user in payload.get("includes", {}).get("users", []):
        if str(user["id"]) == sender or user.get("protected") or str(user["id"]) not in by_author \
                or str(user["id"]) in exclude:
            continue
        evidence = by_author[str(user["id"])][:3]
        score, reasons = score_candidate(user, evidence, terms)
        ranked.append((score, user, evidence, reasons))
    ranked.sort(key=lambda x: (-x[0], x[1]["username"]))
    with rt.factory.begin() as db:
        workspace_lock(db)
        run = SearchRun(query=query, terms=terms, count=len(posts),
                        capped=bool(payload.get("meta", {}).get("next_token")) or len(ranked) > 20
                        or bool(payload.get("errors")))
        if seed:
            run.seed_handles, run.seed_summary = list(seed["handles"]), seed["summary"]
        db.add(run)
        db.flush()
        for score, profile, evidence, reasons in ranked[:20]:
            person = upsert_candidate(db, profile)
            db.add(SearchResult(run_id=run.id, candidate_id=person.x_id, score=score, reasons=reasons))
            for post in evidence:
                eid = str(post["id"])
                item = db.get(Evidence, eid)
                if item is None:
                    item = Evidence(id=eid, candidate_id=person.x_id)
                    db.add(item)
                elif item.content_hash != digest(post["text"]):
                    invalidate_source(db, eid)
                item.text, item.content_hash = post["text"], digest(post["text"])
                item.url = f"https://x.com/{person.handle}/status/{eid}" \
                    if rt.settings.app_mode == "live" else ""
                item.published, item.retrieved, item.available = parse_time(post["created_at"]), now(), True
        return run.id


def invalidate_source(db, eid):
    for outreach in db.scalars(select(Outreach)).all():
        if eid in outreach.selected_sources:
            outreach.approved_hash = None
            outreach.approval_snapshot = None
            outreach.version += 1


def revalidate(rt, ids):
    if not ids:
        return
    payload = rt.read("posts", ids)
    returned = {str(p["id"]): p for p in payload.get("data") or []}
    changed = False
    with rt.factory.begin() as db:
        workspace_lock(db)
        for eid in ids:
            item = db.get(Evidence, eid)
            post = returned.get(eid)
            if item is None:
                raise DomainError("EVIDENCE_UNAVAILABLE", "Select available public evidence.")
            valid = post is not None and str(post.get("author_id")) == item.candidate_id
            new_hash = digest(post["text"]) if valid else ""
            if not valid or item.content_hash != new_hash:
                invalidate_source(db, eid)
                changed = True
            item.available = valid
            item.retrieved = now()
            if valid:
                item.text, item.content_hash = post["text"], new_hash
    if changed:
        raise DomainError("EVIDENCE_CHANGED", "Source evidence changed or disappeared. Review a fresh draft.")
