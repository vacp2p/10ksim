from __future__ import annotations

import pytest

from src.deployments.core.configs.command import (
    Command,
    CommandConfig,
    CommandNotFoundError,
    build_command,
    build_container_command,
)


def test_find_command_raises_when_missing():
    config = CommandConfig(commands=[Command(command="echo", args=["hi"])])
    with pytest.raises(CommandNotFoundError):
        config.find_command("python")


def test_find_command_respects_explicit_default():
    config = CommandConfig(commands=[Command(command="echo", args=["hi"])])
    sentinel = object()
    assert config.find_command("python", default=sentinel) is sentinel


def test_insert_command_appends_by_default():
    config = CommandConfig()
    config.insert_command("echo", ["hello"])
    assert len(config.commands) == 1
    assert config.commands[0].command == "echo"
    assert config.commands[0].args == ["hello"]


def test_insert_commands_appends_multiple():
    config = CommandConfig()
    config.insert_commands(["echo", "pwd"])
    assert [cmd.command for cmd in config.commands] == ["echo", "pwd"]


def test_insert_commands_with_index_inserts_at_position():
    config = CommandConfig(
        commands=[Command(command="first", args=[]), Command(command="third", args=[])]
    )
    config.insert_commands(["second"], index=1)
    assert [cmd.command for cmd in config.commands] == ["first", "second", "third"]


def test_use_single_command_sets_flag():
    config = CommandConfig()
    config.use_single_command()
    assert config.single_k8s_command is True


def test_build_command_returns_none_when_empty():
    config = CommandConfig()
    assert build_command(config) == (None, None)


def test_build_command_single_k8s_command_returns_command_and_args():
    config = CommandConfig(commands=[Command(command="python", args=["app.py"])])
    config.use_single_command(True)
    assert build_command(config) == (["python"], ["app.py"])


def test_build_command_single_k8s_command_raises_for_multiple_commands():
    config = CommandConfig(
        commands=[
            Command(command="python", args=["app.py"]),
            Command(command="echo", args=["done"]),
        ]
    )
    config.use_single_command(True)
    with pytest.raises(ValueError):
        build_command(config)


def test_build_command_script_mode_returns_shell_wrapper():
    config = CommandConfig(
        commands=[
            Command(command="echo", args=["hello"]),
            Command(command="pwd", args=[]),
        ]
    )
    command, args = build_command(config)
    assert command[0:2] == ["sh", "-c"]
    assert args is None
    assert "echo hello" in command[-1]
    assert "pwd" in command[-1]


def test_build_container_command_uses_custom_prefix():
    result = build_container_command(["echo hello"], prefix=["bash", "-lc"])
    assert result == ["bash", "-lc", "echo hello\n"]


def test_add_args_replace_replaces_existing_flag_value_pair():
    command = Command(command="app", args=[("--max-connections", "1000")])
    command.add_args([("--max-connections", "200")], on_duplicate="replace")
    assert command.args == [("--max-connections", "200")]


def test_add_args_replace_consumes_duplicate_existing_args_in_order():
    command = Command(command="app", args=[("--name", "alice"), ("--name", "bob")])
    command.add_args(
        [("--name", "carl"), ("--name", "dave")],
        on_duplicate="replace",
    )
    assert command.args == [("--name", "carl"), ("--name", "dave")]


def test_add_args_replace_appends_new_values_after_replacing_existing_duplicates():
    command = Command(command="app", args=[("--name", "alice"), ("--name", "bob")])
    command.add_args(
        [("--name", "carl"), ("--name", "dave"), ("--name", "eric")],
        on_duplicate="replace",
    )
    assert command.args == [("--name", "carl"), ("--name", "dave"), ("--name", "eric")]
