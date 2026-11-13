"""Local MCP server for The Last King playtest batches."""
import os
import secrets
import subprocess
import sys
from collections import Counter
from pathlib import Path
from threading import Thread
from typing import Annotated, Any, Literal
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from tools.playtest_job import JOBS, job_directory, read_runs, read_status, report_text, summarize, write_status

mcp = FastMCP("The Last King Playtest")
ACTIVE = {"queued", "running"}


def reap_worker(process: subprocess.Popen, directory: Path) -> None:
    if process.wait() != 0:
        status = read_status(directory)
        if status["state"] in ACTIVE:
            status.update(state="failed", current_run=None, detail="Процесс плейтеста прервался.")
            write_status(directory, status)


@mcp.tool(structured_output=True)
def start_playtest(
    runs: Annotated[int, Field(ge=1, le=60)] = 20,
    dungeon: Literal["all", "kar_mord", "forest", "monastery"] = "all",
    turn_limit: Annotated[int, Field(ge=2, le=60)] = 25,
    mode: Literal["live", "fixture"] = "live",
    player: Literal["llm", "rules"] = "llm",
    review: bool = True,
    max_api_calls: Annotated[int | None, Field(ge=1, le=20000)] = None,
    seed: Annotated[int | None, Field(ge=0, le=2**32 - 1)] = None,
    focus: Annotated[str, Field(max_length=800)] = "",
) -> dict[str, Any]:
    """Start an isolated background batch. Live uses the configured OpenAI project. The API request limit can be overridden. Fixture uses zero API calls. Focus is an optional brief for the player and editor."""
    if mode == "live":
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise ValueError("Для живого пакета задайте OPENAI_API_KEY в окружении MCP-сервера.")
        if max_api_calls is None:
            max_api_calls = min(20_000, runs * (5 * (turn_limit + 1) + int(review)))
    else:
        player, review = "rules", False
    job_id = uuid4().hex
    directory = JOBS / job_id
    directory.mkdir(mode=0o700, parents=True)
    status = {
        "id": job_id, "state": "queued", "runs": runs, "completed": 0, "current_run": None,
        "mode": mode, "dungeon": dungeon, "turn_limit": turn_limit, "player": player,
        "review": review, "seed": seed if seed is not None else secrets.randbits(32),
        "focus": focus.strip(), "max_api_calls": max_api_calls if mode == "live" else 0,
        "api_calls": 0, "usage": {},
    }
    if mode == "live":
        status.update(
            gm_model=os.getenv("PLAYTEST_GM_MODEL") or "gpt-5-mini",
            player_model=os.getenv("PLAYTEST_PLAYER_MODEL") or "gpt-5-mini",
            review_model=os.getenv("PLAYTEST_REVIEW_MODEL") or "gpt-5-mini",
        )
    else:
        status.update(gm_model="fixture", player_model="rules", review_model="off")
    write_status(directory, status)
    try:
        with (directory / "worker.log").open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "tools/playtest_batch.py"), str(directory)],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError:
        status.update(state="failed", detail="Не удалось запустить процесс плейтеста.")
        write_status(directory, status)
        raise
    Thread(target=reap_worker, args=(process, directory), daemon=True).start()
    return status


@mcp.tool(structured_output=True)
def get_playtest_status(job_id: str) -> dict[str, Any]:
    """Return progress, API request count, and outcomes for finished runs."""
    directory = job_directory(job_id)
    status = read_status(directory)
    runs = read_runs(directory)
    status["outcomes"] = dict(Counter(run["outcome"] for run in runs))
    return status


@mcp.tool(structured_output=True)
def get_playtest_report(job_id: str) -> dict[str, Any]:
    """Return the Markdown report and grouped findings. It also works while the batch runs."""
    directory = job_directory(job_id)
    status = read_status(directory)
    summary = summarize(read_runs(directory))
    return {"status": status, "summary": summary, "markdown": report_text(status, summary)}


@mcp.tool(structured_output=True)
def get_playtest_run(
    job_id: str, run_number: Annotated[int, Field(ge=1, le=60)],
    from_turn: Annotated[int, Field(ge=0, le=60)] = 0,
    limit: Annotated[int, Field(ge=1, le=12)] = 5,
) -> dict[str, Any]:
    """Read a finished run with a page of actions, narration, dice, and game state. Opening scene is turn 0."""
    directory = job_directory(job_id)
    for run in read_runs(directory):
        if run["number"] == run_number:
            turns = run["turns"][from_turn:from_turn + limit]
            next_turn = from_turn + limit
            return {**run, "turns": turns, "next_turn": next_turn if next_turn < len(run["turns"]) else None}
    raise ValueError("Забег ещё не записан или его номер отсутствует.")


@mcp.tool(structured_output=True)
def stop_playtest(job_id: str) -> dict[str, Any]:
    """Request a stop. An in-flight provider request can finish; saved results remain readable."""
    directory = job_directory(job_id)
    status = read_status(directory)
    if status["state"] in ACTIVE:
        (directory / "cancel").touch()
        return {"id": status["id"], "state": "stop_requested"}
    return {"id": status["id"], "state": status["state"]}


if __name__ == "__main__":
    mcp.run(transport="stdio")
