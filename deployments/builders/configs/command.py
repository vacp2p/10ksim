from collections import defaultdict
from typing import Dict, List, Literal, Optional, SupportsIndex, Tuple, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Command(BaseModel):
    pre_command: Optional[str] = None
    command: str
    args: List[str | Tuple[str, str]] = []
    multiline: bool = False

    def with_pre_command(self, prefix: str, *, overwrite: bool = False):
        if self.pre_command and not overwrite:
            raise ValueError(
                f"Command already has a pre_command. Passed prefix: `{prefix}` Command: `{self}`"
            )
        self.pre_command = prefix

    def add_arg(
        self,
        arg: str | Tuple[str, str],
        *,
        on_duplicate: Literal["error", "replace"] = "error",
    ):
        """Add arg to command.

        `on_duplicate` determines the behavior when an argument with the same key already exists.
        error: raises ValueError
        replace: replaces all instances of the argument in self.args with the single new argument passed in
        """
        self.add_args([arg], on_duplicate=on_duplicate)

    def _add_arg_error(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "error"
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag in existing_args_map:
            existing_flags = [self.args[index] for index in existing_args_map[flag]]
            raise ValueError(
                f"Command already contains flag(s). flag: `{flag}` existing_flags: {existing_flags}"
            )
        self.args.append(arg)

    def _add_arg_ignore(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "ignore"
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag not in existing_args_map:
            self.args.append(arg)

    def _add_arg_replace(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "replace"

        Note: This may modify `existing_args_map` for the caller.
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag in existing_args_map:
            self.args = [item for item in self.args if item != arg]
            # Remove from map so it won't be replaced again.
            del existing_args_map[flag]
            self.args.insert(existing_args_map[flag], arg)
        else:
            self.args.append(arg)

    def add_args(
        self,
        args: List[str | Tuple[str, str]] | Dict[str, str],
        *,
        on_duplicate: Literal["error", "ignore", "replace"] = "error",
    ):
        """Add args to command.

        `on_duplicate` determines the behavior when an argument with the same key already exists.

        `"error"`: raises ValueError if flag existed in self.args when this function was called

        Note: This allows you to have duplicate flags in `args` param and add them to self.args.

        `"ignore"`: does not add the argument

        `"replace"`: replaces all instances of the argument in self.args with all new arguments with the same flag

        Note: This allows you to pass in a new set of flags/value pairs to replace an existing set.

        For example: --name=Alice --name=Bob can be replaced with --name=Alfred --name=Ben --name=Carl
        """
        if isinstance(args, dict):
            args = [(key, value) for key, value in args.items()]

        existing_args_map = defaultdict(list)
        for index, arg in enumerate(self.args):
            existing_args_map[arg].append(index)

        for arg in args:
            if on_duplicate == "error":
                self._add_arg_error(arg, existing_args_map)
            elif on_duplicate == "ignore":
                self._add_arg_ignore(arg, existing_args_map)
            elif on_duplicate == "replace":
                self._add_arg_replace(arg, existing_args_map)
            else:
                raise ValueError(f"Unknown value for argument. on_duplicate: `{on_duplicate}`")

    def __str__(self) -> str:
        args = []
        for arg in self.args:
            if isinstance(arg, str):
                args.append(arg)
            else:
                args.append(f"{arg[0]}={arg[1]}")

        if not args:
            return self.command

        prefix = f"{self.pre_command} " if self.pre_command is not None else ""
        if self.multiline:
            args = [f"  {_arg}" for _arg in args]
            return f"{prefix}{self.command} \\\n" + " \\\n".join(args)
        else:
            return f"{prefix}{self.command} " + " ".join(args)


class CommandNotFoundError(ValueError):
    pass


class CommandConfig(BaseModel):
    commands: List[Command] = []

    single_k8s_command: bool = False
    """When True, then uses the Kubernetes fields "command" and "args"
    instead of a script with each command when building.

    Requires that there is only a single command.
    """

    def use_single_command(self, single_k8s_command: bool = True):
        self.single_k8s_command = single_k8s_command

    def insert_commands(
        self,
        commands: List[str | Command],
        *,
        index: Optional[SupportsIndex] = None,
    ):
        """Insert multiple commands starting at a given index.

        :param commands: List of commands to insert. `str` commands are assumed to have no args.

        :param index: Starting position. If None, appends all commands to the end."""
        indices = (
            [position for position in range(index, len(commands))]
            if index is not None
            else [None for _ in range(len(commands))]
        )
        for insert_index, command in zip(indices, commands):
            if isinstance(command, Command):
                self.commands.insert(insert_index, command)
            else:
                self.insert_command(command, None, multiline=False, index=insert_index)

    def insert_command(
        self,
        command: str,
        args: None | List[str | Tuple[str, Optional[str]]],
        *,
        multiline: bool = False,
        index: Optional[SupportsIndex] = None,
    ):
        if args is None:
            args = []
        if index is None:
            index = len(self.commands)
        self.commands.insert(index, Command(command=command, args=args, multiline=multiline))

    _sentinel = object()

    def find_command(self, command_name: str) -> Command | None:
        """Finds the Command for the given command in the ContainerConfig"""
        result = next(
            (command for command in self.commands if command.command == command_name),
            None,
        )
        if result is CommandConfig._sentinel:
            raise CommandNotFoundError(
                f"Failed to find command in config. name: `{command_name}` config: `{self}`"
            )
        return result


def build_command(config: CommandConfig) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """
    If there are no commands, returns (None, None).

    If config.single_k8s_command is True, then returns `(command : List[str], args : List[str])`

    Otherwise returns a script command with all commands and arguments with None for args: `(command : List[str], None)`

    :rtype: Tuple[Optional[List[str]], Optional[List[str]]]
    :returns: (command, args)
    """
    if not config.commands:
        return None, None
    if config.single_k8s_command:
        if len(config.commands) != 1:
            raise ValueError(
                f"Attempt to build single Kubernetes command with multiple commands. config: `{config}`"
            )
        return [config.commands[0].command], deepcopy(config.commands[0].args)

    command_lines = []
    for command in config.commands:
        command_lines.append(str(command))
    command = build_container_command(command_lines)
    return command, None


def build_container_command(
    command_lines: List[str], prefix: Optional[List[str]] = None
) -> List[str]:
    if prefix is None:
        prefix = ["sh", "-c"]
    # The newline is added to the end of command to prevent chomp in dumped yaml.
    # We want `|` not `|-` in the final output.
    return prefix + ["\n".join(command_lines) + "\n"]
