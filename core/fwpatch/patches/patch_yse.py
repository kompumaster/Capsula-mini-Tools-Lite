"""yse: пакетный менеджер Entware и .yap в разделе data.

Кладёт клиент `yse` в `/data/opt/bin/yse` (в таре раздела data — путь
`opt/bin/yse`), профиль PATH в overlay (`overlay/upper/etc/profile.d/yse.sh`,
виден как `/etc/profile.d/yse.sh`), симлинк `overlay/upper/opt` ->
`/data/opt/entware` (виден как `/opt`) и статический `curl` (musl, mbedTLS)
в `/data/opt/entware/bin/curl` (`/opt/bin/curl`) для HTTPS-загрузок `.yap`.

В скрипте `yse` из обёртки `opkg()` убран `LD_LIBRARY_PATH`: системная
glibc 2.33 обратно совместима с Entware-овской 2.27, а системный
busybox-`wget` (нужный `opkg`) ломается, получив `/opt/lib` (2.27).

Дальше по SSH: `yse bootstrap` (Entware, нужна сеть); для `.yap`-реестров
нужен ещё `awk` — `yse install gawk` (в busybox колонки awk нет).
"""

from __future__ import annotations

from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha, put_asset)

KEY = "yse"
TITLE = "YSE пакеты"
SUMMARY = "пакетный менеджер Entware и .yap"
PART = "data"
KIND = "toggle"
FLAG = "yse"
ORDER = 23

YSE_PATH = "opt/bin/yse"
YSE_ASSET = "yse/yse"
PROFILE_PATH = "overlay/upper/etc/profile.d/yse.sh"
PROFILE_ASSET = "yse/yse_profile.sh"
OPT_LINK = "overlay/upper/opt"
OPT_TARGET = "/data/opt/entware"
CURL_PATH = "opt/entware/bin/curl"
CURL_ASSET = "yse/curl"

FILES = (
    (YSE_PATH, YSE_ASSET, 0o755),
    (PROFILE_PATH, PROFILE_ASSET, 0o644),
    (CURL_PATH, CURL_ASSET, 0o755),
)

LOGICAL = {
    YSE_PATH: "yse",
    PROFILE_PATH: "yse-profile",
    CURL_PATH: "curl",
}


def _drop_link(tree: TarTree, path: str, ask: Ask | None) -> None:
    """Убрать симлинк; чужой файл/каталог — с подтверждением."""
    if not tree.exists(path):
        return
    if tree.kind(path) == "link":
        tree.remove(path)
        return
    if ask is None or not ask(f"{path}: это не наш симлинк; заменить?", True):
        raise PatchError(f"{path}: отменено")
    tree.remove(path)


def _put_link(tree: TarTree, path: str, target: str, ask: Ask | None) -> None:
    if tree.kind(path) == "link" and tree.link_target(path) == target:
        return
    _drop_link(tree, path, ask)
    tree.symlink(path, target)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        put_asset(tree, path, asset, mode, ask)
    _put_link(tree, OPT_LINK, OPT_TARGET, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    _drop_link(tree, OPT_LINK, ask)
    for path, asset, _mode in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — yse, профиль, curl и симлинк на месте и совпадают."""
    hashes = {}
    state = "on"
    for path, asset, _mode in FILES:
        digest = present_sha(tree, path)
        if digest is None:
            state = "off"
            continue
        hashes[LOGICAL[path]] = digest
        if digest != asset_sha(asset):
            state = "off"
    if (tree.kind(OPT_LINK) != "link"
            or tree.link_target(OPT_LINK) != OPT_TARGET):
        state = "off"
    return state, hashes
