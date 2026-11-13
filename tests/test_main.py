"""Тесты для визуализатора графа зависимостей."""

import base64
import gzip
import io
import os
import pathlib
import sys
import tarfile
import tempfile
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import main


def make_config(**over):
    """Возвращает корректную конфигурацию с переопределёнными полями."""
    cfg = {
        "package_name": "nginx",
        "repository_url": "https://test.com/",
        "repository_mode": "remote",
        "package_version": "1.0",
        "output_image": "out.png",
    }
    cfg.update(over)
    return cfg


def write_tmp(text, suffix=".txt"):
    """Создаёт временный файл с текстом и возвращает путь к нему."""
    tmp = tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=suffix, encoding="utf-8")
    tmp.write(text)
    tmp.close()
    return tmp.name


def make_stream(name, content):
    """Возвращает gzip-поток tar с одним файлом без завершающих блоков."""
    buf = io.BytesIO()
    tar = tarfile.TarFile(fileobj=buf, mode="w")
    info = tarfile.TarInfo(name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))
    return gzip.compress(buf.getvalue())


def make_apk(pkginfo):
    """Собирает apk: подпись, управляющий и пустой потоки данных."""
    return (make_stream(".SIGN.RSA.key.rsa.pub", b"sig")
            + make_stream(".PKGINFO", pkginfo.encode())
            + make_stream("usr/bin/x", b"x"))


def test_load_valid_config():
    """Корректный TOML читается."""
    path = write_tmp('package_name = "nginx"\n', ".toml")
    try:
        assert main.load_config(path)["package_name"] == "nginx"
    finally:
        os.remove(path)


def test_config_missing_file():
    """Отсутствующий файл конфигурации даёт ConfigError."""
    with pytest.raises(main.ConfigError):
        main.load_config("no_such_file.toml")


def test_config_bad_toml():
    """Некорректный TOML даёт ConfigError."""
    path = write_tmp("package_name = = =", ".toml")
    try:
        with pytest.raises(main.ConfigError):
            main.load_config(path)
    finally:
        os.remove(path)


@pytest.mark.parametrize("over", [
    {"repository_mode": "ftp"},
    {"package_name": "  "},
    {"package_name": "bad name"},
    {"package_version": "1 0"},
    {"package_version": 5},
    {"output_image": "out.jpg"},
    {"repository_url": "ftp://x"},
])
def test_invalid_config(over):
    """Неверные значения параметров отклоняются."""
    with pytest.raises(main.ConfigError):
        main.validate_config(make_config(**over))


def test_missing_key():
    """Отсутствие параметра отклоняется."""
    cfg = make_config()
    del cfg["package_version"]
    with pytest.raises(main.ConfigError):
        main.validate_config(cfg)


def test_valid_config():
    """Корректная конфигурация проходит проверку."""
    main.validate_config(make_config())


def test_test_mode_file_missing():
    """В режиме test несуществующий файл отклоняется."""
    cfg = make_config(
        repository_mode="test", package_name="A", repository_url="nofile")
    with pytest.raises(main.ConfigError):
        main.validate_config(cfg)


def test_test_mode_capital_names():
    """В режиме test имя пакета - большие латинские буквы."""
    path = write_tmp("A: B\n")
    try:
        bad = make_config(
            repository_mode="test", package_name="a", repository_url=path)
        good = make_config(
            repository_mode="test", package_name="A", repository_url=path)
        with pytest.raises(main.ConfigError):
            main.validate_config(bad)
        main.validate_config(good)
    finally:
        os.remove(path)


PKGINFO = (
    "pkgname = nginx\n"
    "depend = so:libc.musl-x86_64.so.1\n"
    "depend = pcre2\n"
    "depend = pcre2\n"
)


def test_read_pkginfo_from_multistream_apk():
    """.PKGINFO читается из apk (несколько gzip-потоков подряд)."""
    text = main.read_pkginfo(make_apk(PKGINFO))
    assert "pkgname = nginx" in text


def test_read_pkginfo_not_archive():
    """Не архив даёт RepositoryError."""
    with pytest.raises(main.RepositoryError):
        main.read_pkginfo(b"not an archive")


def test_read_pkginfo_missing():
    """Архив без .PKGINFO даёт RepositoryError."""
    with pytest.raises(main.RepositoryError):
        main.read_pkginfo(make_stream("other", b"x"))


def test_parse_depends():
    """Зависимости читаются в исходном виде, повторы убираются."""
    deps = main.parse_depends(PKGINFO)
    assert deps == ["so:libc.musl-x86_64.so.1", "pcre2"]


def test_apk_url():
    """URL пакета строится из репозитория, имени и версии."""
    url = main.apk_url("https://r/x86_64/", "nginx", "1.0-r1")
    assert url == "https://r/x86_64/nginx-1.0-r1.apk"


def test_get_direct_dependencies_from_repository():
    """Пакет скачивается по URL репозитория, зависимости извлекаются."""
    with tempfile.TemporaryDirectory() as tmp:
        apk = pathlib.Path(tmp) / "nginx-1.0.apk"
        apk.write_bytes(make_apk(PKGINFO))
        url = pathlib.Path(tmp).as_uri()
        deps = main.get_direct_dependencies(url, "nginx", "1.0")
    assert deps == ["so:libc.musl-x86_64.so.1", "pcre2"]


def test_get_direct_dependencies_wrong_version():
    """Отсутствующая версия пакета даёт RepositoryError."""
    with tempfile.TemporaryDirectory() as tmp:
        url = pathlib.Path(tmp).as_uri()
        with pytest.raises(main.RepositoryError):
            main.get_direct_dependencies(url, "nginx", "9.9")


INDEX_TEXT = """C:Q1abc
P:nginx
V:1.24.0-r7

P:musl
V:1.2.4-r2
p:so:libc.musl-x86_64.so.1=1

P:pcre2
V:10.42-r1

P:nginx-common
V:1.24.0-r7
"""

PKGINFOS = {
    "nginx": "depend = so:libc.musl-x86_64.so.1\ndepend = pcre2\n"
             "depend = /bin/sh\ndepend = !conflict\ndepend = nginx-common\n",
    "pcre2": "depend = so:libc.musl-x86_64.so.1\n",
    "musl": "pkgname = musl\n",
    "nginx-common": "depend = musl>=1.0\n",
}


def test_apkindex_resolve():
    """so:-записи разрешаются в пакеты, конфликты и файлы пропускаются."""
    idx = main.ApkIndex(main.parse_apkindex(INDEX_TEXT))
    assert idx.resolve("so:libc.musl-x86_64.so.1") == "musl"
    assert idx.resolve("nginx-common>=1.0") == "nginx-common"
    assert idx.resolve("!nginx") is None
    assert idx.resolve("/bin/sh") is None
    assert idx.resolve("unknown") is None


def test_remote_repo_dependencies():
    """Зависимости корня берутся для заданной версии."""
    idx = main.ApkIndex(main.parse_apkindex(INDEX_TEXT))
    seen = []

    def fetch(name, version):
        """Фиктивная загрузка: запоминает запрошенную версию."""
        seen.append((name, version))
        return main.parse_depends(PKGINFOS[name])

    repo = main.RemoteRepo(idx, "nginx", "1.24.0-r7", fetch)
    deps = repo.dependencies("nginx")
    assert deps == ["musl", "pcre2", "nginx-common"]
    assert seen == [("nginx", "1.24.0-r7")]


def test_remote_repo_unknown_package():
    """Пакет вне индекса даёт RepositoryError."""
    idx = main.ApkIndex(main.parse_apkindex(INDEX_TEXT))
    repo = main.RemoteRepo(idx, "nginx", "1", lambda n, v: [])
    with pytest.raises(main.RepositoryError):
        repo.dependencies("nope")


def test_full_remote_graph():
    """Весь путь: индекс и пакеты скачиваются из репозитория."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = pathlib.Path(tmp)
        index = make_stream("APKINDEX", INDEX_TEXT.encode())
        (folder / "APKINDEX.tar.gz").write_bytes(index)
        versions = {"nginx": "1.24.0-r7", "pcre2": "10.42-r1",
                    "musl": "1.2.4-r2", "nginx-common": "1.24.0-r7"}
        for name, version in versions.items():
            apk = make_apk(PKGINFOS[name])
            (folder / f"{name}-{version}.apk").write_bytes(apk)
        config = make_config(
            repository_url=folder.as_uri(), package_version="1.24.0-r7")
        repo = main.make_repo(config)
        graph, cycles = main.build_graph_dfs("nginx", repo.dependencies)
    assert graph["nginx"] == ["musl", "pcre2", "nginx-common"]
    assert graph["pcre2"] == ["musl"]
    assert graph["musl"] == []
    assert cycles == []


def test_dfs_transitive():
    """Граф включает транзитивные зависимости."""
    repo = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
    graph, cycles = main.build_graph_dfs("A", lambda n: repo.get(n, []))
    assert set(graph) == {"A", "B", "C", "D"}
    assert cycles == []


def test_dfs_cycle():
    """Цикл обнаруживается и не вызывает зацикливания."""
    repo = {"A": ["B"], "B": ["C"], "C": ["A"]}
    graph, cycles = main.build_graph_dfs("A", lambda n: repo.get(n, []))
    assert set(graph) == {"A", "B", "C"}
    assert cycles == [["A", "B", "C", "A"]]


def test_dfs_self_cycle():
    """Зависимость пакета от самого себя считается циклом."""
    graph, cycles = main.build_graph_dfs("A", lambda n: ["A"])
    assert cycles == [["A", "A"]]


def test_dfs_single_package():
    """Пакет без зависимостей даёт граф из одной вершины."""
    graph, cycles = main.build_graph_dfs("A", lambda n: [])
    assert graph == {"A": []}
    assert cycles == []


def test_load_test_repo():
    """Тестовый репозиторий читается, комментарии игнорируются."""
    path = write_tmp("# комментарий\nA: B C\nB: C\nC:\n")
    try:
        expected = {"A": ["B", "C"], "B": ["C"], "C": []}
        assert main.load_test_repo(path) == expected
    finally:
        os.remove(path)


def test_load_test_repo_bad_name():
    """Имя не из больших латинских букв отклоняется."""
    path = write_tmp("A: b\n")
    try:
        with pytest.raises(main.RepositoryError):
            main.load_test_repo(path)
    finally:
        os.remove(path)


def test_load_test_repo_bad_format():
    """Строка без двоеточия отклоняется."""
    path = write_tmp("A B\n")
    try:
        with pytest.raises(main.RepositoryError):
            main.load_test_repo(path)
    finally:
        os.remove(path)


def test_make_repo_test_mode_unknown_root():
    """Корень, которого нет в тестовом файле, отклоняется."""
    path = write_tmp("A: B\n")
    try:
        config = make_config(
            repository_mode="test", package_name="Z", repository_url=path)
        with pytest.raises(main.RepositoryError):
            main.make_repo(config)
    finally:
        os.remove(path)


def test_print_cycles(capsys):
    """Циклы выводятся в виде цепочки."""
    main.print_cycles([["A", "B", "A"]])
    assert "A -> B -> A" in capsys.readouterr().out


def test_plantuml_generation():
    """Текст PlantUML содержит рёбра и обрамление."""
    text = main.generate_plantuml({"nginx": ["libc"], "libc": []}, "nginx")
    assert "@startuml" in text
    assert "[nginx] --> [libc]" in text
    assert "[libc]" in text
    assert "@enduml" in text


def test_plantuml_encode_roundtrip():
    """Кодирование для сервера обратимо."""
    source = "@startuml\n[A] --> [B]\n@enduml"
    enc = main.plantuml_encode(source)
    table = str.maketrans(main.BASE64_PUML, main.BASE64_STD)
    std = enc.translate(table)
    std += "=" * (-len(std) % 4)
    raw = zlib.decompress(base64.b64decode(std), main.DEFLATE_RAW_WBITS)
    assert raw.decode() == source


def fake_server(tmp, text, content):
    """Подменяет сервер PlantUML папкой с файлом-ответом."""
    folder = pathlib.Path(tmp)
    (folder / main.plantuml_encode(text)).write_bytes(content)
    main.PLANTUML_SERVER = folder.as_uri() + "/"


def test_render_server_saves_png():
    """PNG-ответ сервера сохраняется в файл."""
    old = main.PLANTUML_SERVER
    text = main.generate_plantuml({"A": []}, "A")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fake_server(tmp, text, b"\x89PNG data")
            png = os.path.join(tmp, "g.png")
            main.render_server(text, png)
            assert open(png, "rb").read().startswith(b"\x89PNG")
    finally:
        main.PLANTUML_SERVER = old


def test_render_server_rejects_non_png():
    """Ответ сервера, не являющийся PNG, отклоняется."""
    old = main.PLANTUML_SERVER
    text = main.generate_plantuml({"A": []}, "A")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fake_server(tmp, text, b"<html>error</html>")
            with pytest.raises(main.RepositoryError):
                main.render_server(text, os.path.join(tmp, "g.png"))
    finally:
        main.PLANTUML_SERVER = old
