"""Инструмент визуализации графа зависимостей пакетов Alpine Linux (apk).

Этап 5: визуализация - описание графа на PlantUML и PNG.
"""

import base64
import functools
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zlib

try:
    import tomllib
except ImportError:
    print("Ошибка: требуется Python 3.11 или новее.", file=sys.stderr)
    sys.exit(1)

DEFAULT_CONFIG = "config.toml"
REQUIRED_KEYS = [
    "package_name", "repository_url", "repository_mode",
    "package_version", "output_image",
]
VALID_MODES = ["remote", "test"]
NAME_PATTERN = r"^[A-Za-z0-9._+-]+$"
VERSION_PATTERN = r"^[A-Za-z0-9._+~-]+$"
TEST_NAME_PATTERN = r"^[A-Z]+$"


class ConfigError(Exception):
    """Ошибка конфигурации."""


HTTP_TIMEOUT = 60
USER_AGENT = {"User-Agent": "depgraph/1.0"}
PKGINFO_NAME = ".PKGINFO"
DEPEND_PREFIX = "depend = "


class RepositoryError(Exception):
    """Ошибка получения данных о репозитории или пакете."""


sys.setrecursionlimit(10000)

INDEX_NAME = "APKINDEX"
INDEX_ARCHIVE = "APKINDEX.tar.gz"
FIELD_PREFIX_LEN = 2
CONSTRAINT_PATTERN = r"[=<>~]"


PLANTUML_SERVER = "https://www.plantuml.com/plantuml/png/"
PNG_SIGNATURE = b"\x89PNG"
DEFLATE_LEVEL = 9
DEFLATE_RAW_WBITS = -15
BASE64_STD = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)
BASE64_PUML = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)


def load_config(filepath: str) -> dict:
    """Читает TOML-файл конфигурации."""
    if not os.path.isfile(filepath):
        raise ConfigError(f"Файл конфигурации не найден: {filepath}")
    try:
        with open(filepath, "rb") as file:
            return tomllib.load(file)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"Некорректный TOML: {err}")


def check_required_keys(config: dict) -> None:
    """Проверяет наличие, тип и непустоту всех параметров."""
    for key in REQUIRED_KEYS:
        if key not in config:
            raise ConfigError(f"Отсутствует параметр: '{key}'")
        if not isinstance(config[key], str):
            raise ConfigError(f"Параметр '{key}' должен быть строкой")
        if not config[key].strip():
            raise ConfigError(f"Параметр '{key}' не может быть пустым")


def check_remote_params(config: dict) -> None:
    """Проверяет параметры режима remote."""
    if not re.match(r"^https?://", config["repository_url"]):
        raise ConfigError(
            "В режиме remote repository_url должен начинаться "
            "с http:// или https://")
    if not re.match(NAME_PATTERN, config["package_name"]):
        raise ConfigError(
            "Недопустимое имя пакета (разрешены буквы, цифры, . _ + -)")
    if not re.match(VERSION_PATTERN, config["package_version"]):
        raise ConfigError("Недопустимый формат версии пакета")


def check_test_params(config: dict) -> None:
    """Проверяет параметры режима test."""
    if not os.path.isfile(config["repository_url"]):
        raise ConfigError(
            f"Файл тестового репозитория не найден: "
            f"{config['repository_url']}")
    if not re.match(TEST_NAME_PATTERN, config["package_name"]):
        raise ConfigError(
            "В режиме test имя пакета должно состоять "
            "из больших латинских букв")


def validate_config(config: dict) -> None:
    """Проверяет все параметры конфигурации."""
    check_required_keys(config)
    mode = config["repository_mode"]
    if mode not in VALID_MODES:
        raise ConfigError(
            f"repository_mode должен быть одним из {VALID_MODES}, "
            f"получено: '{mode}'")
    if not config["output_image"].lower().endswith(".png"):
        raise ConfigError("output_image должен иметь расширение .png")
    if mode == "remote":
        check_remote_params(config)
    else:
        check_test_params(config)


def http_get(url: str) -> bytes:
    """Скачивает содержимое по URL."""
    try:
        request = urllib.request.Request(url, headers=USER_AGENT)
        return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT).read()
    except (urllib.error.URLError, OSError) as err:
        raise RepositoryError(f"Не удалось скачать {url}: {err}")


def apk_url(repo_url: str, name: str, version: str) -> str:
    """Формирует URL файла пакета в репозитории apk."""
    return f"{repo_url.rstrip('/')}/{name}-{version}.apk"


def read_pkginfo(data: bytes) -> str:
    """Достаёт текст файла .PKGINFO из apk-пакета."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar:
                if member.name == PKGINFO_NAME:
                    raw = tar.extractfile(member).read()
                    return raw.decode("utf-8", errors="replace")
    except (tarfile.TarError, OSError, EOFError) as err:
        raise RepositoryError(f"Повреждённый apk-пакет: {err}")
    raise RepositoryError("В пакете нет файла .PKGINFO")


def parse_depends(pkginfo: str) -> list:
    """Возвращает записи 'depend = ...' из .PKGINFO без повторов."""
    result = []
    for line in pkginfo.splitlines():
        if line.startswith(DEPEND_PREFIX):
            dep = line[len(DEPEND_PREFIX):].strip()
            if dep and dep not in result:
                result.append(dep)
    return result


def get_direct_dependencies(repo_url: str, name: str, version: str) -> list:
    """Скачивает пакет заданной версии и возвращает его зависимости."""
    data = http_get(apk_url(repo_url, name, version))
    return parse_depends(read_pkginfo(data))


def strip_constraint(text: str) -> str:
    """Отбрасывает версионное ограничение у имени (nginx>=1.0 -> nginx)."""
    return re.split(CONSTRAINT_PATTERN, text)[0].strip()


def parse_block(block: str) -> dict:
    """Разбирает один блок APKINDEX в словарь полей 'X:значение'."""
    fields = {}
    for line in block.splitlines():
        if len(line) >= FIELD_PREFIX_LEN and line[1] == ":":
            fields[line[0]] = line[FIELD_PREFIX_LEN:].strip()
    return fields


def parse_apkindex(text: str) -> list:
    """Разбирает текст APKINDEX: блоки разделены пустой строкой."""
    entries = []
    for block in text.split("\n\n"):
        fields = parse_block(block)
        if "P" in fields and "V" in fields:
            entries.append({
                "name": fields["P"],
                "version": fields["V"],
                "provides": fields.get("p", "").split(),
            })
    return entries


class ApkIndex:
    """Индекс репозитория: версии пакетов и виртуальные имена (so:, cmd:)."""

    def __init__(self, entries: list):
        """Строит словари версий и provides."""
        self.versions = {}
        self.provides = {}
        for entry in entries:
            self.versions[entry["name"]] = entry["version"]
            for prov in entry["provides"]:
                name = strip_constraint(prov)
                self.provides.setdefault(name, entry["name"])

    def resolve(self, dep: str):
        """Приводит запись зависимости к имени пакета или None."""
        if dep.startswith("!") or dep.startswith("/"):
            return None
        name = strip_constraint(dep)
        if name in self.versions:
            return name
        return self.provides.get(name)


def read_index_text(data: bytes) -> str:
    """Достаёт текст файла APKINDEX из архива APKINDEX.tar.gz."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar:
                if member.name == INDEX_NAME:
                    raw = tar.extractfile(member).read()
                    return raw.decode("utf-8", errors="replace")
    except (tarfile.TarError, OSError, EOFError) as err:
        raise RepositoryError(f"Повреждённый {INDEX_ARCHIVE}: {err}")
    raise RepositoryError(f"В архиве нет файла {INDEX_NAME}")


def download_index(repo_url: str) -> ApkIndex:
    """Скачивает индекс репозитория (нужен для версий и provides)."""
    data = http_get(f"{repo_url.rstrip('/')}/{INDEX_ARCHIVE}")
    return ApkIndex(parse_apkindex(read_index_text(data)))


class RemoteRepo:
    """Источник зависимостей: репозиторий apk по URL."""

    def __init__(self, index, root: str, root_version: str, fetch):
        """fetch(name, version) возвращает записи depend из .PKGINFO."""
        self.index = index
        self.root = root
        self.root_version = root_version
        self.fetch = fetch

    def version_of(self, name: str) -> str:
        """Версия пакета: у корня задана пользователем, у прочих из индекса."""
        if name == self.root:
            return self.root_version
        if name not in self.index.versions:
            raise RepositoryError(f"Пакет '{name}' не найден в репозитории")
        return self.index.versions[name]

    def dependencies(self, name: str) -> list:
        """Прямые зависимости пакета в виде имён пакетов."""
        result = []
        for dep in self.fetch(name, self.version_of(name)):
            real = self.index.resolve(dep)
            if real and real != name and real not in result:
                result.append(real)
        return result


class FileRepo:
    """Источник зависимостей: файл тестового репозитория."""

    def __init__(self, graph: dict):
        """Сохраняет граф, прочитанный из файла."""
        self.graph = graph

    def dependencies(self, name: str) -> list:
        """Прямые зависимости пакета."""
        return self.graph.get(name, [])


def parse_test_line(path: str, number: int, line: str):
    """Разбирает строку 'A: B C' тестового репозитория."""
    if ":" not in line:
        raise RepositoryError(
            f"{path}, строка {number}: ожидается формат 'A: B C'")
    name, deps = line.split(":", 1)
    name, deps = name.strip(), deps.split()
    for pkg in [name] + deps:
        if not re.match(TEST_NAME_PATTERN, pkg):
            raise RepositoryError(
                f"{path}, строка {number}: имя '{pkg}' должно состоять "
                f"из больших латинских букв")
    return name, deps


def load_test_repo(path: str) -> dict:
    """Читает файл тестового репозитория (формат строки: 'A: B C')."""
    graph = {}
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            line = line.split("#")[0].strip()
            if not line:
                continue
            name, deps = parse_test_line(path, number, line)
            known = graph.setdefault(name, [])
            known.extend(d for d in deps if d not in known)
    return graph


def make_repo(config: dict):
    """Создаёт источник зависимостей по режиму из конфигурации."""
    root = config["package_name"]
    if config["repository_mode"] == "test":
        graph = load_test_repo(config["repository_url"])
        if root not in graph:
            raise RepositoryError(
                f"Пакет '{root}' не описан в тестовом репозитории")
        return FileRepo(graph)
    url = config["repository_url"]
    fetch = functools.partial(get_direct_dependencies, url)
    return RemoteRepo(
        download_index(url), root, config["package_version"], fetch)


def dfs_visit(node: str, get_deps, graph: dict, path: list, cycles: list):
    """Рекурсивный шаг DFS: заполняет граф и список найденных циклов."""
    path.append(node)
    deps = get_deps(node)
    graph[node] = deps
    for dep in deps:
        if dep in path:
            cycles.append(path[path.index(dep):] + [dep])
        elif dep not in graph:
            dfs_visit(dep, get_deps, graph, path, cycles)
    path.pop()


def build_graph_dfs(root: str, get_deps):
    """Строит граф зависимостей рекурсивным DFS.

    Возвращает (graph, cycles). Циклы не приводят к зацикливанию:
    посещённая вершина повторно не обходится, цикл запоминается.
    """
    graph, cycles = {}, []
    dfs_visit(root, get_deps, graph, [], cycles)
    return graph, cycles


def print_cycles(cycles: list) -> None:
    """Выводит найденные циклические зависимости."""
    if not cycles:
        return
    print("Обнаружены циклические зависимости:")
    for cycle in cycles:
        print("  " + " -> ".join(cycle))


def generate_plantuml(graph: dict, root: str = "") -> str:
    """Возвращает текстовое представление графа на языке PlantUML."""
    lines = ["@startuml"]
    if root:
        lines.append(f"title Зависимости: {root}")
    for pkg, deps in graph.items():
        if not deps:
            lines.append(f"[{pkg}]")
        for dep in deps:
            lines.append(f"[{pkg}] --> [{dep}]")
    lines.append("@enduml")
    return "\n".join(lines)


def plantuml_encode(text: str) -> str:
    """Кодирует текст для сервера PlantUML (raw deflate + свой base64)."""
    comp = zlib.compressobj(DEFLATE_LEVEL, zlib.DEFLATED, DEFLATE_RAW_WBITS)
    raw = comp.compress(text.encode("utf-8")) + comp.flush()
    encoded = base64.b64encode(raw).decode().rstrip("=")
    return encoded.translate(str.maketrans(BASE64_STD, BASE64_PUML))


def render_local(local: str, puml_file: str, png_file: str) -> None:
    """Строит PNG локально установленным plantuml."""
    subprocess.run([local, "-tpng", puml_file], check=True)
    produced = os.path.splitext(puml_file)[0] + ".png"
    if os.path.abspath(produced) != os.path.abspath(png_file):
        shutil.move(produced, png_file)


def render_server(puml_text: str, png_file: str) -> None:
    """Получает PNG от сервера PlantUML."""
    data = http_get(PLANTUML_SERVER + plantuml_encode(puml_text))
    if not data.startswith(PNG_SIGNATURE):
        raise RepositoryError("Сервер PlantUML вернул не PNG")
    with open(png_file, "wb") as file:
        file.write(data)


def save_graph(graph: dict, root: str, output_image: str) -> None:
    """Сохраняет описание .puml и изображение .png."""
    text = generate_plantuml(graph, root)
    puml_file = os.path.splitext(output_image)[0] + ".puml"
    with open(puml_file, "w", encoding="utf-8") as file:
        file.write(text)
    print(f"PlantUML-описание сохранено: {puml_file}")
    local = shutil.which("plantuml")
    if local:
        render_local(local, puml_file, output_image)
    else:
        render_server(text, output_image)
    print(f"Изображение сохранено: {output_image}")


def main() -> None:
    """Точка входа: строит граф и сохраняет его в PlantUML и PNG."""
    args = sys.argv[1:]
    config_path = args[0] if args else DEFAULT_CONFIG
    try:
        config = load_config(config_path)
        validate_config(config)
        repo = make_repo(config)
        root = config["package_name"]
        graph, cycles = build_graph_dfs(root, repo.dependencies)
        print(f"Пакетов в графе: {len(graph)}")
        print_cycles(cycles)
        save_graph(graph, root, config["output_image"])
    except (ConfigError, RepositoryError) as err:
        print(f"Ошибка: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
