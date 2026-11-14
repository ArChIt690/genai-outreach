import re
from datetime import UTC, datetime

import httpx

from app.errors import ProviderError

SCOPES = "tweet.read users.read dm.read dm.write offline.access"


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class XClient:
    """Official API only. A send request is never retried."""
    def __init__(self, token, transport=None):
        self.http = httpx.Client(
            base_url="https://api.x.com", headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(20, connect=5), transport=transport, follow_redirects=False,
        )

    def close(self):
        self.http.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise ProviderError("X_NETWORK_UNCERTAIN") from None
        if response.status_code >= 400:
            codes = {401: "ACCOUNT_RECONNECT_REQUIRED", 403: "X_PERMISSION_OR_RECIPIENT_RESTRICTED",
                     404: "X_RESOURCE_UNAVAILABLE", 429: "RATE_LIMITED", 402: "X_CREDITS_REQUIRED"}
            reset = response.headers.get("x-rate-limit-reset")
            retry_at = datetime.fromtimestamp(int(reset), UTC) if reset and reset.isdigit() else None
            raise ProviderError(
                codes.get(response.status_code, "X_REQUEST_REJECTED"), response.status_code,
                definitive=response.status_code in {400, 401, 402, 403, 404, 409, 422, 429}, retry_at=retry_at,
            )
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("X_MALFORMED_RESPONSE") from None
        if not isinstance(data, dict):
            raise ProviderError("X_MALFORMED_RESPONSE")
        return data

    def me(self):
        data = self.request("GET", "/2/users/me").get("data")
        if not data or not str(data.get("id", "")).isdigit():
            raise ProviderError("X_MALFORMED_RESPONSE")
        return data

    def user(self, handle):
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            raise ProviderError("INVALID_HANDLE", 400, True)
        data = self.request("GET", f"/2/users/by/username/{handle}",
                            params={"user.fields": "description,location,protected"}).get("data")
        if not data or not str(data.get("id", "")).isdigit():
            raise ProviderError("X_RESOURCE_UNAVAILABLE", 404, True)
        return data

    def search(self, query, limit=50):
        return self.request("GET", "/2/tweets/search/recent", params={
            "query": query, "max_results": max(10, min(50, limit)), "expansions": "author_id",
            "tweet.fields": "created_at,author_id",
            "user.fields": "description,location,protected",
        })

    def posts(self, ids):
        return self.request("GET", "/2/tweets", params={
            "ids": ",".join(ids), "tweet.fields": "created_at,author_id",
        })

    def events(self, recipient, cursor=None):
        if not str(recipient).isdigit():
            raise ProviderError("INVALID_RECIPIENT", 400, True)
        params = {"max_results": 20, "dm_event.fields": "created_at,sender_id,dm_conversation_id",
                  "event_types": "MessageCreate"}
        if cursor:
            params["pagination_token"] = cursor
        return self.request("GET", f"/2/dm_conversations/with/{recipient}/dm_events", params=params)

    def send(self, recipient, text):
        if not str(recipient).isdigit():
            raise ProviderError("INVALID_RECIPIENT", 400, True)
        payload = self.request("POST", f"/2/dm_conversations/with/{recipient}/messages",
                               json={"text": text})
        data = payload.get("data") or {}
        if not data.get("dm_event_id") or not data.get("dm_conversation_id"):
            raise ProviderError("X_MALFORMED_SUCCESS")
        return data
