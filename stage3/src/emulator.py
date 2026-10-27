#!/usr/bin/env python3
"""
Эмулятор shell. Этапы 1-3.
Вариант №21.
"""

import argparse
import getpass
import os
import shlex
import shutil
import socket
import sys

ENV_VAR_PREFIX_LEN = 1
BRACKET_OFFSET = 2
EXPECTED_ARGS_CD = 1
EXPECTED_ARGS_SAVE = 1


class VNode:
    """Узел виртуальной файловой системы (файл или папка)."""

    def __init__(self, name: str, is_dir: bool, content: str = "") -> None:
        self.name = name
        self.is_dir = is_dir
        self.content = content
        self.children = {}


class VFS:
    """Виртуальная файловая система в памяти."""

    def __init__(self) -> None:
        self.root = VNode("/", is_dir=True)

    def load(self, path: str) -> None:
        """Загружает VFS из физической директории."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"VFS path not found: {path}")
        if not os.path.isdir(path):
            raise ValueError(f"VFS source is not a directory: {path}")
        self.root = VNode("/", is_dir=True)
        self._load_dir(self.root, path)

    def _load_dir(self, node: VNode, disk_path: str) -> None:
        for name in sorted(os.listdir(disk_path)):
            full = os.path.join(disk_path, name)
            if os.path.isdir(full):
                child = VNode(name, is_dir=True)
                node.children[name] = child
                self._load_dir(child, full)
            elif os.path.isfile(full):
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    node.children[name] = VNode(name, False, content)

    def save(self, path: str) -> None:
        """Сохраняет VFS на физический диск."""
        if os.path.exists(path) and not os.path.isdir(path):
            raise ValueError(f"target is not a directory: {path}")
        os.makedirs(path, exist_ok=True)
        for name in os.listdir(path):
            p = os.path.join(path, name)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        self._save_dir(self.root, path)

    def _save_dir(self, node: VNode, disk_path: str) -> None:
        for name, child in node.children.items():
            full = os.path.join(disk_path, name)
            if child.is_dir:
                os.makedirs(full, exist_ok=True)
                self._save_dir(child, full)
            else:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(child.content)


def expand_vars(token: str, env: dict) -> str:
    """Раскрывает переменные окружения вида $VAR и ${VAR}."""
    result = ""
    i = 0
    while i < len(token):
        if token[i] == '$':
            if i + 1 < len(token) and token[i + 1] == '{':
                j = token.find('}', i + BRACKET_OFFSET)
                if j != -1:
                    name = token[i + BRACKET_OFFSET:j]
                    result += env.get(name, "")
                    i = j + 1
                    continue
            else:
                j = i + ENV_VAR_PREFIX_LEN
                while j < len(token) and (token[j].isalnum() or token[j] == '_'):
                    j += 1
                name = token[i + ENV_VAR_PREFIX_LEN:j]
                if name:
                    result += env.get(name, "")
                    i = j
                    continue
        result += token[i]
        i += 1
    return result


def parse(line: str, env: dict) -> list:
    """Разбивает строку на токены."""
    return [expand_vars(t, env) for t in shlex.split(line)]


def get_prompt() -> str:
    """Формирует приглашение к вводу на основе данных ОС."""
    try:
        username = getpass.getuser()
    except Exception:
        username = "user"
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "host"
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = cwd.replace(home, "~", 1)
    return f"{username}@{hostname}:{cwd}$ "


def cmd_exit(args: list) -> bool:
    """Обработка команды exit."""
    if len(args) > 0:
        print("exit: no arguments expected", file=sys.stderr)
        return True
    return False


def cmd_ls(args: list) -> bool:
    """Заглушка для команды ls."""
    print(f"ls: args={args}")
    return True


def cmd_cd(args: list) -> bool:
    """Заглушка для команды cd с проверкой аргументов."""
    if len(args) != EXPECTED_ARGS_CD:
        print("cd: wrong number of arguments", file=sys.stderr)
        return True
    print(f"cd: args={args}")
    return True


def cmd_vfs_save(vfs: VFS, args: list) -> bool:
    """Команда сохранения VFS."""
    if vfs is None:
        print("vfs-save: VFS not loaded", file=sys.stderr)
        return True
    if len(args) != EXPECTED_ARGS_SAVE:
        print("vfs-save: exactly one argument required", file=sys.stderr)
        return True
    try:
        vfs.save(args[0])
        print(f"VFS saved to {args[0]}")
    except Exception as e:
        print(f"vfs-save: {e}", file=sys.stderr)
    return True


def execute(vfs: VFS, line: str, env: dict) -> bool:
    """Выполняет одну строку ввода."""
    line = line.strip()
    if not line:
        return True
    try:
        tokens = parse(line, env)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return True
    if not tokens:
        return True

    cmd_name = tokens[0]
    args = tokens[1:]

    if cmd_name == "exit":
        return cmd_exit(args)
    elif cmd_name == "ls":
        return cmd_ls(args)
    elif cmd_name == "cd":
        return cmd_cd(args)
    elif cmd_name == "vfs-save":
        return cmd_vfs_save(vfs, args)
    else:
        print(f"{cmd_name}: command not found", file=sys.stderr)
        return True


def run_interactive(vfs: VFS, env: dict) -> None:
    """Запускает основной цикл REPL."""
    print("Эмулятор оболочки ОС запущен.")
    print("Введите 'exit' для выхода.")
    while True:
        try:
            user_input = input(get_prompt())
            if not execute(vfs, user_input, env):
                break
        except (KeyboardInterrupt, EOFError):
            print("\nВыход...")
            break


def run_script(vfs: VFS, script_path: str, env: dict) -> None:
    """Режим выполнения стартового скрипта."""
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: cannot read startup script: {e}", file=sys.stderr)
        return
    for raw in lines:
        line = raw.rstrip("\n")
        print(f"{get_prompt()}{line}")
        if not execute(vfs, line, env):
            return


def main() -> None:
    """Точка входа."""
    parser = argparse.ArgumentParser(description="Shell emulator")
    parser.add_argument("--vfs", help="path to VFS directory")
    parser.add_argument("--script", help="path to startup script")
    args = parser.parse_args()

    print(f"[DEBUG] vfs    = {args.vfs}")
    print(f"[DEBUG] script = {args.script}")

    vfs = None
    if args.vfs:
        vfs = VFS()
        try:
            vfs.load(args.vfs)
            print(f"[DEBUG] VFS loaded into memory from {args.vfs}")
        except Exception as e:
            print(f"error loading VFS: {e}", file=sys.stderr)
            sys.exit(1)

    env = os.environ

    if args.script:
        run_script(vfs, args.script, env)
    else:
        run_interactive(vfs, env)


if __name__ == "__main__":
    main()