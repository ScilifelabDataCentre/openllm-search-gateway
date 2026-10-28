"""Checks for the search gateway (app.py).

Run from the repo root, with plain Python 3.10 or newer and nothing installed:

    python3 tests/test_gateway.py

FastAPI and DDGS are replaced by small stand-ins, and the endpoints are called
as plain functions. Nothing leaves the machine. The checks for the Open WebUI
tool and assistant live in openllm-setup, next to those files.
"""

# cspell:ignore bing ddgs DDGS duckduckgo fastapi importlib openwebui OPENWEBUI

import asyncio
import os
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---- stand-ins for FastAPI and DDGS (the real ones run in the image) ----
fastapi = types.ModuleType("fastapi")
responses = types.ModuleType("fastapi.responses")


class FastAPI:
    def get(self, path):
        return lambda f: f

    def post(self, path):
        return lambda f: f


class Response:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code


fastapi.FastAPI, fastapi.Header = FastAPI, (lambda default=None: default)
responses.JSONResponse = Response
searches = []  # every search that would have gone to DuckDuckGo
ddgs = types.ModuleType("ddgs")


class DDGS:
    def text(self, query, max_results, backend):
        searches.append((query, backend))
        return [{"title": "T", "href": "https://example.org", "body": "B"}]


ddgs.DDGS = DDGS
sys.modules.update({"fastapi": fastapi, "fastapi.responses": responses, "ddgs": ddgs})
os.environ.update(API_KEY="test", OPENWEBUI_URL="https://owu.example/", MAX_WAITING_PER_USER="3")

import app as gateway  # noqa: E402  (after the stand-ins)

run = asyncio.run
KEY = "Bearer test"


def search(query, user="u1", chat="c1", key=KEY):
    return run(gateway.search({"query": query, "count": 3}, authorization=key,
                              x_openwebui_user_id=user, x_openwebui_chat_id=chat))


def answer(rid, user, decision):
    return run(gateway.answer(rid, {"user": user, "decision": decision}, authorization=KEY))


# The API key is required everywhere
assert search("x", key="Bearer wrong").status_code == 401
assert run(gateway.approval("x", user="u1", authorization="")).status_code == 401

# A new search sends nothing and returns an approval with a link into Open WebUI
r = search("sepsis guidelines")
rid = r[0]["approval_id"]
assert r[0]["link"].startswith("https://owu.example/?model=search_approvals&q=") and r[0]["link"].endswith(rid)
assert r[0]["message"] and not searches and "sepsis" not in r[0]["link"]  # the search text is never in the link
assert r[0]["session_hours"] == 8
assert search("sepsis guidelines")[0]["approval_id"] == rid  # asked again: the same approval, not a second one

# Only the user who searched can see or answer the approval
assert run(gateway.approval(rid, user="u1", authorization=KEY))["query"] == "sepsis guidelines"
assert run(gateway.approval(rid, user="u2", authorization=KEY)).status_code == 404
assert answer(rid, "u2", "once").status_code == 404
assert answer(rid, "u1", "maybe").status_code == 400

# Approve once: the same search runs once, on DuckDuckGo only
assert answer(rid, "u1", "once") == {"status": "allowed"}
assert answer(rid, "u1", "decline") == {"status": "allowed"}  # the first answer counts
assert search("sepsis guidelines")[0]["link"] == "https://example.org"
assert searches[-1] == ("sepsis guidelines", "duckduckgo")
assert "approval_id" in search("sepsis guidelines")[0]  # once means once

# Decline: reported once, nothing sent
d = search("declined search", chat="c2")[0]["approval_id"]
answer(d, "u1", "decline")
n = len(searches)
assert search("declined search", chat="c2")[0]["title"] == "Search declined" and len(searches) == n

# Session: covers the same chat and user only, until it ends
s = search("first", chat="c3")[0]["approval_id"]
assert answer(s, "u1", "session") == {"status": "session"} and s not in gateway.approvals
assert search("first", chat="c3")[0]["link"] == "https://example.org"
assert search("something else", chat="c3")[0]["link"] == "https://example.org"
assert "approval_id" in search("something else", chat="c4")[0]  # another chat: asked again
assert "approval_id" in search("something else", user="u2", chat="c3")[0]  # another user: asked again
gateway.sessions[("u1", "c3")] = time.time() - 1
assert "approval_id" in search("after the end", chat="c3")[0]  # the session ended

# Searches without a chat (terminals and agents) share one session per user
t = search("from a terminal", user="u3", chat="")[0]["approval_id"]
answer(t, "u3", "session")
assert search("another terminal search", user="u3", chat="")[0]["link"] == "https://example.org"

# Limits and expiry
for q in ("w1", "w2"):
    search(q, user="u5")
assert "approval_id" in search("w3", user="u5")[0]
assert search("w4", user="u5")[0]["title"] == "Too many searches waiting"
old = search("old", user="u6")[0]["approval_id"]
gateway.approvals[old]["created"] -= 10_000
assert run(gateway.approval(old, user="u6", authorization=KEY)).status_code == 404

# A failing search engine gives a clear message
DDGS.text = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("refused"))
f = search("engine down", user="u7")[0]["approval_id"]
answer(f, "u7", "once")
assert search("engine down", user="u7")[0]["title"] == "Search failed"

assert run(gateway.healthz()) == {"ok": True}

# SEARCH_ENGINE: DuckDuckGo by default, another single engine when set, never "auto" or a list
import importlib  # noqa: E402

assert gateway.SEARCH_ENGINE == "duckduckgo"
DDGS.text = lambda self, query, max_results, backend: (searches.append((query, backend)), [])[1]
os.environ["SEARCH_ENGINE"] = "Bing "
gateway = importlib.reload(gateway)
gateway.run_search("engine check", 3)
assert searches[-1] == ("engine check", "bing")
for refused in ("auto", "", "duckduckgo,bing"):
    os.environ["SEARCH_ENGINE"] = refused
    try:
        importlib.reload(gateway)
        raise AssertionError(f"SEARCH_ENGINE={refused!r} should be refused")
    except SystemExit:
        pass

print("all checks passed")
