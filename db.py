"""MongoDB data layer for the board bot.

Everything is scoped per-guild (server). Two collections:

`persons` — the board. One doc per tracked name:
    {
        "_id": "<guild_id>:<name_lower>",
        "guild_id": int,
        "name": str,            # display name as entered
        "name_lower": str,      # normalized, for lookup/uniqueness
        "added_by": int,        # user id
        "created_at": datetime,
        "last_mention_at": datetime | None,
        "last_mention_by": int | None,
    }

`mentions` — per-user tallies. One doc per (name, user):
    {
        "_id": "<guild_id>:<name_lower>:<user_id>",
        "guild_id": int,
        "name_lower": str,
        "user_id": int,
        "count": int,
        "last_at": datetime,
    }
"""

import os
from datetime import datetime, timezone

import motor.motor_asyncio
from pymongo import ReturnDocument

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(name: str) -> str:
    return name.strip().lower()


def _db():
    global _client
    if _client is None:
        uri = os.environ.get("MONGO_URI")
        if not uri:
            raise RuntimeError("MONGO_URI is not set in your .env file.")
        # tz_aware=True so datetimes come back timezone-aware (UTC), which lets
        # us subtract them from _now() without "naive vs aware" errors.
        _client = motor.motor_asyncio.AsyncIOMotorClient(uri, tz_aware=True)
    return _client["counterbot"]


def _persons():
    return _db()["persons"]


def _mentions():
    return _db()["mentions"]


async def ping() -> None:
    """Raise if the database is unreachable. Used as a startup health check."""
    await _db().command("ping")


async def ensure_indexes() -> None:
    await _persons().create_index([("guild_id", 1)])
    await _mentions().create_index([("guild_id", 1), ("name_lower", 1), ("count", -1)])
    await _mentions().create_index([("guild_id", 1), ("user_id", 1)])


# --- the board (persons) ---

async def add_person(
    guild_id: int, name: str, added_by: int, user_id: int | None = None
) -> bool:
    """Add a name. Returns False if it already exists.

    `user_id` links the person to a real Discord member (set when added by tag),
    which lets auto-detect also fire on @mentions of that member.
    """
    name = name.strip()
    nl = _norm(name)
    if await _persons().find_one({"_id": f"{guild_id}:{nl}"}):
        return False
    await _persons().insert_one(
        {
            "_id": f"{guild_id}:{nl}",
            "guild_id": guild_id,
            "name": name,
            "name_lower": nl,
            "user_id": user_id,
            "added_by": added_by,
            "created_at": _now(),
            "last_mention_at": None,
            "last_mention_by": None,
        }
    )
    return True


async def get_person(guild_id: int, name: str) -> dict | None:
    return await _persons().find_one({"_id": f"{guild_id}:{_norm(name)}"})


async def list_persons(guild_id: int) -> list[dict]:
    cursor = _persons().find({"guild_id": guild_id}).sort("name_lower", 1)
    return [doc async for doc in cursor]


async def list_person_names(guild_id: int) -> list[str]:
    return [doc["name"] for doc in await list_persons(guild_id)]


async def remove_person(guild_id: int, name: str) -> tuple[bool, int]:
    """Remove a name and all of its mention tallies.

    Returns (was_removed, number_of_mention_records_deleted).
    """
    nl = _norm(name)
    result = await _persons().delete_one({"_id": f"{guild_id}:{nl}"})
    deleted = await _mentions().delete_many({"guild_id": guild_id, "name_lower": nl})
    return result.deleted_count > 0, deleted.deleted_count


# --- the core action ---

async def log_mention(guild_id: int, name: str, user_id: int) -> tuple[dict | None, int | None]:
    """Record that `name` was mentioned by `user_id`.

    Resets the clock, sets the last-mentioner, and bumps that user's tally.
    Returns (person_doc_BEFORE_update, new_user_count), or (None, None) if the
    person isn't on the board. The pre-update doc lets the caller report the
    streak that was just broken.
    """
    nl = _norm(name)
    prev = await _persons().find_one_and_update(
        {"_id": f"{guild_id}:{nl}"},
        {"$set": {"last_mention_at": _now(), "last_mention_by": user_id}},
        return_document=ReturnDocument.BEFORE,
    )
    if prev is None:
        return None, None
    tally = await _mentions().find_one_and_update(
        {"_id": f"{guild_id}:{nl}:{user_id}"},
        {
            "$inc": {"count": 1},
            "$set": {
                "guild_id": guild_id,
                "name_lower": nl,
                "user_id": user_id,
                "last_at": _now(),
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return prev, tally["count"]


# --- reads ---

async def total_mentions(guild_id: int, name: str) -> int:
    nl = _norm(name)
    pipeline = [
        {"$match": {"guild_id": guild_id, "name_lower": nl}},
        {"$group": {"_id": None, "t": {"$sum": "$count"}}},
    ]
    docs = await _mentions().aggregate(pipeline).to_list(length=1)
    return docs[0]["t"] if docs else 0


async def leaderboard(guild_id: int, name: str, limit: int = 10) -> list[dict]:
    nl = _norm(name)
    cursor = (
        _mentions()
        .find({"guild_id": guild_id, "name_lower": nl})
        .sort("count", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def active_players(guild_id: int) -> set[int]:
    """Everyone who has ever mentioned *anyone* in this guild."""
    return set(await _mentions().distinct("user_id", {"guild_id": guild_id}))


async def mentioners_of(guild_id: int, name: str) -> set[int]:
    """Everyone who has mentioned this specific person."""
    nl = _norm(name)
    return set(
        await _mentions().distinct(
            "user_id", {"guild_id": guild_id, "name_lower": nl}
        )
    )


async def top_mentioner(guild_id: int, name: str) -> dict | None:
    """The single biggest mentioner of this person, or None."""
    nl = _norm(name)
    rows = (
        await _mentions()
        .find({"guild_id": guild_id, "name_lower": nl})
        .sort("count", -1)
        .limit(1)
        .to_list(1)
    )
    return rows[0] if rows else None


async def rank_of(guild_id: int, name: str, user_id: int) -> int | None:
    """A user's 1-based rank on a person's leaderboard, or None if absent."""
    nl = _norm(name)
    me = await _mentions().find_one({"_id": f"{guild_id}:{nl}:{user_id}"})
    if not me:
        return None
    higher = await _mentions().count_documents(
        {"guild_id": guild_id, "name_lower": nl, "count": {"$gt": me["count"]}}
    )
    return higher + 1


async def totals_by_person(guild_id: int) -> dict[str, int]:
    """All-time mention totals keyed by name_lower (one query for the board)."""
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$group": {"_id": "$name_lower", "t": {"$sum": "$count"}}},
    ]
    return {d["_id"]: d["t"] async for d in _mentions().aggregate(pipeline)}


async def totals_by_user(guild_id: int) -> dict[int, int]:
    """All-time mention totals keyed by user_id, across every person."""
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$group": {"_id": "$user_id", "t": {"$sum": "$count"}}},
    ]
    return {d["_id"]: d["t"] async for d in _mentions().aggregate(pipeline)}


async def favorite_target(guild_id: int, user_id: int) -> dict | None:
    """The person this user has mentioned most (their top mention doc), or None."""
    rows = (
        await _mentions()
        .find({"guild_id": guild_id, "user_id": user_id})
        .sort("count", -1)
        .limit(1)
        .to_list(1)
    )
    return rows[0] if rows else None


async def mentioned_names_by_user(guild_id: int) -> dict[int, set]:
    """For each user, the set of name_lowers they've mentioned at least once."""
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$group": {"_id": "$user_id", "names": {"$addToSet": "$name_lower"}}},
    ]
    return {d["_id"]: set(d["names"]) async for d in _mentions().aggregate(pipeline)}


# --- temporary roles (for the /gay easter egg) ---

async def add_temp_role(guild_id: int, role_id: int, user_id: int, expires_at) -> None:
    await _db()["temp_roles"].insert_one(
        {
            "_id": role_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "expires_at": expires_at,
        }
    )


async def due_temp_roles(now) -> list[dict]:
    """Temp roles whose expiry has passed and should be cleaned up."""
    cursor = _db()["temp_roles"].find({"expires_at": {"$lte": now}})
    return [doc async for doc in cursor]


async def delete_temp_role(role_id: int) -> None:
    await _db()["temp_roles"].delete_one({"_id": role_id})


# --- horny jail sentences ---

async def add_jail(guild_id: int, user_id: int, role_id, expires_at) -> None:
    await _db()["jails"].update_one(
        {"_id": f"{guild_id}:{user_id}"},
        {
            "$set": {
                "guild_id": guild_id,
                "user_id": user_id,
                "role_id": role_id,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )


async def due_jails(now) -> list[dict]:
    """Jail sentences whose time is up."""
    cursor = _db()["jails"].find({"expires_at": {"$lte": now}})
    return [doc async for doc in cursor]


async def active_jails() -> list[dict]:
    """All jail records (used to rebuild in-memory state after a restart)."""
    cursor = _db()["jails"].find({})
    return [doc async for doc in cursor]


async def delete_jail(guild_id: int, user_id: int) -> None:
    await _db()["jails"].delete_one({"_id": f"{guild_id}:{user_id}"})
