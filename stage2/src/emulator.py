#!/usr/bin/env python3
"""
Эмулятор shell. Этапы 1-2.
Вариант №21.
"""

import argparse
import getpass
import os
import shlex
import socket
import sys

ENV_VAR_PREFIX_LEN = 1
BRACKET_OFFSET = 2
EXPECTED_ARGS_CD = 1


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
    """Разбивает строку на токены и раскрывает переменные."""
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


COMMANDS = {
    "exit": cmd_exit,
    "ls": cmd_ls,
    "cd": cmd_cd,
}


def execute(line: str, env: dict) -> bool:
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

    handler = COMMANDS.get(cmd_name)

    if handler is None:
        print(f"{cmd_name}: command not found", file=sys.stderr)
        return True

    try:
        return handler(args)
    except Exception as e:
        print(f"{cmd_name}: {e}", file=sys.stderr)
        return True


def run_interactive(env: dict) -> None:
    """Запускает основной цикл REPL."""
    print("Эмулятор оболочки ОС запущен.")
    print("Введите 'exit' для выхода.")
    while True:
        try:
            user_input = input(get_prompt())
            if not execute(user_input, env):
                break
        except (KeyboardInterrupt, EOFError):
            print("\nВыход...")
            break


def run_script(script_path: str, env: dict) -> None:
    """Режим выполнения стартового скрипта."""
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        error_msg = f"error: cannot read startup script: {e}"
        print(error_msg, file=sys.stderr)
        return

    for raw in lines:
        line = raw.rstrip("\n")
        print(f"{get_prompt()}{line}")
        if not execute(line, env):
            return


def main() -> None:
    """Точка входа в программу."""
    parser = argparse.ArgumentParser(description="Shell emulator")
    parser.add_argument("--vfs", help="path to VFS directory")
    parser.add_argument("--script", help="path to startup script")
    args = parser.parse_args()

    print(f"[DEBUG] vfs    = {args.vfs}")
    print(f"[DEBUG] script = {args.script}")

    env = os.environ

    if args.script:
        run_script(args.script, env)
    else:
        run_interactive(env)


if __name__ == "__main__":
    main()