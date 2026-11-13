from datetime import timedelta

from sqlalchemy import select

from app.errors import ProviderError
from app.models import FixtureMessage, now

PROFILES = [
    {"id": "fixture_ada", "username": "ada_robotics", "name": "Ada Tan",
     "description": "Robotics researcher building open manipulation tools.", "location": "Singapore"},
    {"id": "fixture_noah", "username": "noah_builds", "name": "Noah Lim",
     "description": "Founder. Developer tools for evaluating AI agents.", "location": "Kuala Lumpur"},
    {"id": "fixture_mira", "username": "mira_models", "name": "Mira Nguyen",
     "description": "Research engineer working on embodied AI.", "location": "Ho Chi Minh City"},
    {"id": "fixture_news", "username": "robot_news", "name": "Robotics Daily",
     "description": "Robotics and AI news from around the world.", "location": ""},
    {"id": "fixture_test", "username": "test_recipient", "name": "Controlled test recipient",
     "description": "Synthetic recipient for testing this prototype.", "location": ""},
]
TEXTS = [
    ("p_ada_1", "fixture_ada", "I'm building an open robotics manipulation benchmark. Released our first evaluation scripts today."),
    ("p_ada_2", "fixture_ada", "Our robotics lab is testing grasp recovery with low-cost arms."),
    ("p_noah", "fixture_noah", "We built a small AI evaluation tool to reproduce failures in tool-using agents."),
    ("p_mira", "fixture_mira", "I'm researching embodied AI. Our robotics experiments compare policies across simulated environments."),
    ("p_news", "fixture_news", "A startup has released a new robotics benchmark. Here is the latest AI news."),
]


class FixtureClient:
    def __init__(self, factory):
        self.factory = factory

    def close(self):
        pass

    def me(self):
        return {"id": "fixture_sender", "username": "prototype_operator", "name": "Prototype operator"}

    def user(self, handle):
        for profile in PROFILES:
            if profile["username"] == handle:
                return profile.copy()
        raise ProviderError("X_RESOURCE_UNAVAILABLE", 404, True)

    def search(self, query):
        terms = [x.lower() for x in query.split('"')[1::2]]
        posts = self.posts([x[0] for x in TEXTS])["data"]
        if terms:
            posts = [p for p in posts if any(t in p["text"].lower() for t in terms)]
        return {"data": posts, "includes": {"users": [x.copy() for x in PROFILES]},
                "meta": {"result_count": len(posts)}}

    def posts(self, ids):
        return {"data": [
            {"id": i, "author_id": author, "text": text,
             "created_at": (now() - timedelta(hours=4)).isoformat()}
            for i, author, text in TEXTS if i in ids
        ]}

    def events(self, recipient, cursor=None):
        with self.factory() as db:
            rows = db.scalars(select(FixtureMessage).where(
                FixtureMessage.recipient_id == recipient).order_by(FixtureMessage.created.desc())).all()
            offset = int(cursor or 0)
            page = rows[offset:offset + 20]
            meta = {}
            if len(rows) > offset + 20:
                meta["next_token"] = str(offset + 20)
            return {"data": [
                {"id": r.id, "sender_id": r.sender_id, "text": r.text,
                 "dm_conversation_id": f"fixture_sender:{recipient}",
                 "created_at": r.created.isoformat()} for r in page
            ], "meta": meta}

    def send(self, recipient, text):
        if not recipient.startswith("fixture_"):
            raise ProviderError("FIXTURE_ID_REQUIRED", 400, True)
        with self.factory.begin() as db:
            row = FixtureMessage(recipient_id=recipient, sender_id="fixture_sender", text=text)
            db.add(row)
            db.flush()
            return {"dm_event_id": row.id, "dm_conversation_id": f"fixture_sender:{recipient}"}
