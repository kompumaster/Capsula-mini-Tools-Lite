# Патчи Lite: как добавить свой

Каждый патч — модуль в этой папке с метаданными и функциями. Меню,
CLI, `status.txt` и имя образа собираются из реестра `__init__.py`.

## Метаданные

| Поле | Что |
|---|---|
| `KEY` | ключ в `status.txt` и имени образа; у существующих не менять |
| `TITLE` | название в меню |
| `PART` | `system_b` или `data` |
| `KIND` | `toggle` (вкл/выкл) или `kill` (только заглушка) |
| `FLAG` | CLI: `--<FLAG>-on/off` для `toggle`, `--<FLAG>-kill` для `kill` |
| `ORDER` | порядок в `status.txt`, имени образа и внутри группы меню; в меню сначала все `toggle`, затем `kill` |

## Функции

`toggle`:

- `apply(tree, ask=None)` — включить;
- `remove(tree, ask=None)` — выключить;
- `detect(tree) -> (state, hashes)` — `"on"`/`"off"` и `{имя: sha256}`.

`kill`:

- `kill(tree)` — заменить оригинал заглушкой;
- `detect(tree) -> (state, hashes)` — `"on"` — оригинал, `"off"` — файла
  нет или стоит заглушка.

`tree` — `TarTree`: правка tar в памяти (`exists`, `kind`, `sha256`,
`read`, `add`, `replace`, `remove`, `ensure_dir`). На диск дерево не
распаковывается.

## Шаблон

```python
"""Мой патч: что делает."""

from fwpatch.tar_tree import TarTree

from .common import Ask, drop, present_sha, put

KEY = "mykey"
TITLE = "Мой патч"
PART = "system_b"
KIND = "toggle"
FLAG = "mykey"
ORDER = 70

PATH = "etc/my.conf"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put(tree, PATH, b"on", 0o644, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop(tree, PATH, b"on", ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "on" if tree.read(PATH).strip() == b"on" else "off"
    return state, {PATH: digest}
```

Для `kill` вместо `apply`/`remove`:

```python
from .common import kill_stub, present_sha, stub_hashes

NAME = "mydaemon"
PATH = f"usr/bin/{NAME}"


def kill(tree: TarTree) -> None:
    kill_stub(tree, PATH, "noop")


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "off" if digest in stub_hashes() else "on"
    return state, {NAME: digest}
```

## Регистрация

Реестр проверяется при импорте: `PART` из `PART_ORDER`, известный
`KIND`, наличие функций, уникальность `KEY`/`FLAG`/`ORDER`. Ошибка —
`PatchError` с именем модуля.

Добавить модуль в `__init__.py`:

```python
from . import patch_mykey

REGISTRY = (..., patch_mykey)
```

`ORDER` задаёт место; `PATCHES`, `KILLS` и `BY_PART` считаются сами.

## Правила

- `KEY` — часть формата: у существующих патчей не переименовывать.
- `PART` — только `system_b`/`data`; новый раздел требует правки
  `PART_ORDER` и отдельного решения.
- `detect()` ничего не меняет в дереве.
- В NAND патчер не пишет: только tar и сборка образа.

## Проверка

```sh
_venv/bin/python core/tests/test_fwpatch_patches.py -v
```

Тест полноты требует, чтобы каждый `patch_*.py` был в `REGISTRY`;
проверяются уникальность `KEY`/`FLAG`/`ORDER` и работа `detect`.
