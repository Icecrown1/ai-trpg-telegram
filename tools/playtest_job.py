"""Storage shared by the local playtest worker and the MCP tools."""
import json
import os
from collections import Counter
from pathlib import Path
from statistics import median
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
JOBS = Path(os.getenv("PLAYTEST_JOB_DIR", ROOT / "playtest_jobs")).expanduser().resolve()


FINDING_TITLES = {
    "hp_outside_bounds": "Здоровье вне допустимых границ",
    "backpack_overflow": "Ресурсов больше, чем вмещает рюкзак",
    "duplicate_inventory": "Повтор предметов в инвентаре",
    "roll_math": "Сумма броска не совпадает с журналом",
    "system_markup_in_story": "Служебный текст в повествовании",
    "haul_summary_mismatch": "Сводка выхода расходится с содержимым рюкзака",
    "city_resources_mismatch": "Склад получил неверное количество ресурсов",
    "city_gold_mismatch": "Казна получила неверное количество золота",
    "thorin_not_in_city": "Спасение Торина не сохранилось",
    "failed_opening_keeps_run_slot": "Сбой первой сцены оставил списанную попытку или занятого искателя",
    "opening_failure_response": "Неожиданный ответ при сбое первой сцены",
    "missing_actions": "Мастер не предложил варианты действий",
    "hp_drop_without_damage_roll": "HP снизилось без видимого броска урона",
    "mixed_script": "Посторонние символы или смесь алфавитов",
    "review_continuity": "Нарушение связности сцены или расхождение с броском",
    "review_choice_clarity": "Неясный выбор",
    "review_language": "Язык и стиль",
    "review_repetition": "Повторы",
    "editor_no_result": "Редактор не вернул ответ",
    "player_fallback": "Пришлось использовать действия по правилам",
    "review_api_error": "Ошибка запроса к редактору",
    "run_start_http": "Ошибка HTTP в начале забега",
    "turn_http": "Ошибка HTTP во время хода",
    "worker_error": "Ошибка процесса плейтеста",
}


def write_status(directory: Path, status: dict) -> None:
    temporary = directory / f".status-{uuid4().hex}.json"
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(directory / "status.json")


def job_directory(job_id: str) -> Path:
    try:
        name = UUID(job_id).hex
    except ValueError:
        raise ValueError("Некорректный ID пакета") from None
    directory = JOBS / name
    if not (directory / "status.json").is_file():
        raise ValueError("Пакет не найден")
    return directory


def read_status(directory: Path) -> dict:
    return json.loads((directory / "status.json").read_text(encoding="utf-8"))


def read_runs(directory: Path) -> list[dict]:
    path = directory / "runs.jsonl"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.endswith("\n")]


def append_run(directory: Path, run: dict) -> None:
    with (directory / "runs.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(run, ensure_ascii=False) + "\n")


def summarize(runs: list[dict]) -> dict:
    outcomes = Counter(run["outcome"] for run in runs)
    checks = successes = 0
    latencies = []
    grouped = {}
    for run in runs:
        for turn in run["turns"]:
            latencies.append(turn["seconds"])
            for roll in turn["rolls"]:
                if "dc" in roll:
                    checks += 1
                    successes += roll.get("success") is True
        for issue in run["findings"]:
            key = (issue["category"], issue["code"])
            group = grouped.setdefault(key, {
                "category": issue["category"], "code": issue["code"], "count": 0, "examples": [],
            })
            group["count"] += 1
            if len(group["examples"]) < 3:
                group["examples"].append({"run": run["number"], **issue})
    return {
        "outcomes": dict(outcomes),
        "moves": sum(len(run["turns"]) - bool(run["turns"]) for run in runs),
        "response_seconds": {"median": median(latencies), "max": max(latencies)} if latencies else {},
        "checks": checks,
        "successful_checks": successes,
        "findings": sorted(grouped.values(), key=lambda group: (
            ("bug", "suspect", "text").index(group["category"]), -group["count"], group["code"],
        )),
    }


def report_text(status: dict, summary: dict) -> str:
    lines = [
        "# The Last King · плейтест", "",
        f'Пакет `{status["id"]}` · Git `{status.get("revision", "unknown")}`',
        f'Состояние **{status["state"]}** · обработано {status["completed"]}/{status["runs"]} · '
        f'API-запросов {status["api_calls"]}/{status["max_api_calls"]}.',
        f'Мастер `{status.get("gm_model", "—")}` · игрок `{status.get("player_model", "—")}` · '
        f'редактор `{status.get("review_model", "—")}`.',
        f'Токены по ответам API: {status.get("usage", {})}',
        f'Исходы: {summary["outcomes"] or "—"}. Ходов: {summary["moves"]}. '
        f'Успешных проверок: {summary["successful_checks"]}/{summary["checks"]}.', "",
    ]
    if timing := summary["response_seconds"]:
        lines += [f'Ответ игрового сервера: медиана {timing["median"]:.2f} с, максимум {timing["max"]:.2f} с.', ""]
    if status.get("focus"):
        lines += [f'Фокус пакета «{status["focus"]}».', ""]
    if status.get("detail"):
        lines += [status["detail"], ""]
    for category, title in (
        ("bug", "Подтверждено проверками"),
        ("suspect", "Нужно перепроверить"),
        ("text", "Предложения по тексту и кнопкам"),
    ):
        lines += [f"## {title}", ""]
        groups = [group for group in summary["findings"] if group["category"] == category]
        if not groups:
            lines += ["Пусто.", ""]
        for group in groups:
            title = FINDING_TITLES.get(group["code"], group["code"])
            lines += [f'### {title} · {group["count"]}', ""]
            for item in group["examples"]:
                evidence = " ".join(item["evidence"].split())
                lines.append(f'- Забег {item["run"]}, ход {item["turn"]}. «{evidence}»')
                if item.get("explanation"):
                    lines.append(f'  {item["explanation"]}')
                if item["suggestion"]:
                    lines.append(f'  Вариант замены «{item["suggestion"]}»')
            lines.append("")
    return "\n".join(lines)
