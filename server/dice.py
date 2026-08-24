"""Honest dice: rolled with the system CSPRNG on the backend,
never invented by the model. The player sees every roll."""
import secrets


def roll(sides: int, count: int = 1, modifier: int = 0, reason: str = "", dc: int | None = None) -> dict:
    sides = max(2, min(int(sides), 100))
    count = max(1, min(int(count), 10))
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    total = sum(rolls) + int(modifier)
    result = {
        "sides": sides,
        "count": count,
        "modifier": int(modifier),
        "rolls": rolls,
        "total": total,
        "reason": reason or "",
    }
    if dc is not None:
        try:
            result["dc"] = int(dc)
            result["success"] = total >= int(dc)
        except (TypeError, ValueError):
            pass
    return result


def roll_3d6() -> int:
    return sum(secrets.randbelow(6) + 1 for _ in range(3))
