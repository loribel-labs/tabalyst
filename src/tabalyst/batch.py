"""Batch planning shared by the commands: inputs, outputs and safe writing.

Every command resolves its inputs, maps each one to its outputs and rejects the
whole batch before any work when the plan is unsafe: output name collisions,
outputs that would replace an input, or existing outputs without ``force``.
"""

import glob
import os
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from tabalyst.errors import ConfigurationError, InputError, ReportError


def path_key(path: Path) -> str:
    """Identity of a path for comparisons, whatever its spelling and case."""
    return os.path.normcase(str(path.resolve()))


def resolve_input_specs(input_specs: Sequence[str | Path]) -> list[Path]:
    """Resolve explicit files and shell-independent, non-recursive glob patterns."""
    if not input_specs:
        raise ConfigurationError("At least one input file is required.")

    sources: list[Path] = []
    known: set[str] = set()
    for value in input_specs:
        text = os.fspath(value)
        if "**" in text:
            raise ConfigurationError(
                f"Recursive input patterns are not supported yet: {text}"
            )
        if glob.has_magic(text):
            matches = sorted(
                (Path(match) for match in glob.glob(text) if Path(match).is_file()),
                key=path_key,
            )
            if not matches:
                raise InputError(f'Input pattern matched no files: "{text}"')
        else:
            path = Path(text)
            if not path.exists():
                raise InputError(f"Input file does not exist: {path}")
            if not path.is_file():
                raise InputError(f"Input path is not a file: {path}")
            matches = [path]

        for path in matches:
            key = path_key(path)
            if key not in known:
                sources.append(path)
                known.add(key)
    return sources


def plan_outputs(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None,
    output_dir: str | Path | None,
    output_name: Callable[[Path], str],
) -> list[tuple[Path, Path]]:
    """Resolve the inputs and pair each one with its main output.

    ``output`` names the output of a single input; otherwise each output is
    named ``output_name(source)``, in ``output_dir`` or beside its source.
    """
    if output is not None and output_dir is not None:
        raise ConfigurationError("--output and --output-dir cannot be used together.")
    sources = resolve_input_specs(input_specs)
    if output is not None and len(sources) != 1:
        raise ConfigurationError("--output can only be used with one input file.")

    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None and destination.exists() and not destination.is_dir():
        raise ReportError(f"Output directory path is a file: {destination}")
    return [
        (
            source,
            Path(output)
            if output is not None
            else (destination if destination is not None else source.parent)
            / output_name(source),
        )
        for source in sources
    ]


def validate_outputs(
    artifacts: Iterable[tuple[Path, Path]],
    *,
    sources: Iterable[Path],
    force: bool,
    label: str,
) -> None:
    """Reject unsafe ``(source, output)`` pairs of a whole batch.

    ``label`` names the outputs in messages, such as ``"Report"``.
    """
    input_keys = {path_key(source) for source in sources}
    owners: dict[str, Path] = {}
    existing: list[Path] = []
    for source, artifact in artifacts:
        if artifact.exists() and artifact.is_dir():
            raise InputError(f"{label} path is a directory: {artifact}")
        key = path_key(artifact)
        if key in input_keys:
            raise InputError(f"{label} would overwrite an input file: {artifact}")
        previous = owners.get(key)
        if previous is not None:
            raise ReportError(
                "Output name collision: "
                f"{previous} and {source} both map to {artifact}."
            )
        owners[key] = source
        if not force and artifact.exists():
            existing.append(artifact)
    if existing:
        lines = "\n".join(f"  {path}" for path in existing)
        raise ReportError(
            f"{label} output already exists. Use --force to replace it:\n" + lines
        )


def write_text_atomic(path: Path, content: str) -> None:
    """Write through a temporary file in the target directory, then replace.

    An interrupted write never leaves a partial file at ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        # mkstemp creates the file for its owner only; give the result the
        # permissions of a plain write under the current umask.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temporary, 0o666 & ~umask)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
