# Python packaging and PyPI release

## Goal

Tabalyst is distributed on [PyPI](https://pypi.org/project/tabalyst/) as the
official Python package `tabalyst`.

The package supports two uses:

- as a Python library through the public API `tabalyst.analyze()`;
- as a command-line application through the `tabalyst` command.

The standard user installation comes from PyPI:

```console
pip install tabalyst
```

The official source repository is `loribel-labs/tabalyst`.

## Overall architecture

Distributable Python code lives in the `src/` layout. The importable package is
`tabalyst`. Package configuration is centralized in `pyproject.toml`.

The project uses setuptools as its build backend. This choice is deliberately
kept: the project was already correctly configured and no migration was needed
to publish on PyPI.

The CLI and the library use the same Tabalyst engine. The CLI is only an
interface over the public API and has no independent analysis engine.

## Public API

The main Python entry point is `tabalyst.analyze()`. It centralizes:

- configuration resolution;
- CSV reading;
- Tabalyst analysis;
- canonical JSON production;
- HTML report generation;
- the `executions.json` history update.

The goal is to keep users from depending on the internal package structure.

## CLI

Installing the package creates the `tabalyst` command. The main syntax uses the
`report` command, a source file and an explicit HTML output:

```console
tabalyst report data.csv -o reports/report.html
```

The same behavior is available with `python -m tabalyst`.

Earlier alpha syntaxes are not kept. The CLI may change incompatibly while the
product remains in alpha.

## Output files

An analysis normally produces an HTML report and a JSON profile with the same
base name. For example, a report named `report.html` also produces
`report.json`.

The same folder also contains `executions.json`. Unlike the two other files,
`executions.json` is cumulative: it holds the history of the analyses run in
that folder, so several reports can share the same `executions.json`.

Its `schema_version` field is the version of the history format. It is
independent of the Tabalyst version recorded in each execution.

## Analysis configuration

Tabalyst accepts some parameters directly from the API or the CLI, such as the
delimiter and the encoding. A JSON configuration file can also be provided.

Configuration precedence is always:

1. a value explicitly provided by the user;
2. a value from the JSON configuration file;
3. the Tabalyst default.

This resolution is centralized so that the CLI and the Python API behave exactly
the same. Current defaults include a comma delimiter and the `utf-8-sig`
encoding.

## Package version

The official package version is defined in `pyproject.toml` and must be unique
for each PyPI publication. This value is the source of truth.

`tabalyst.__version__` reads the installed version from the package metadata,
so the version number is not maintained by hand in several places. From an
uninstalled development copy, Tabalyst can also read it from the repository's
`pyproject.toml`.

The project follows this versioning convention:

- `0.1.0` for an initial functional version;
- `0.1.1`, `0.1.2` and so on for compatible fixes;
- `0.2.0` for a larger functional change;
- `1.0.0` once the public API is considered stable enough.

## Building the package

The build produces two standard Python distributions in `dist/`:

- a wheel;
- a source distribution (sdist).

These files are build artifacts and must not be committed.

The package also includes the resources needed to generate the report, such as
the templates and static resources used by Tabalyst. They must work from the
installed package, without depending on paths relative to the Git repository.

## Testing the package

Validation is not limited to running the source tests. The built wheel must also
be installed and run in an environment independent of the repository. This
catches:

- resources missing from the package;
- imports that only work from the repository;
- dependency declaration errors;
- CLI entry point problems.

CI automates these checks.

## Continuous integration

The main GitHub Actions workflow is `.github/workflows/ci.yml`. It checks
Tabalyst on the supported Python versions, currently Python 3.11 to 3.14, and
runs the tests, Ruff, the package build and a wheel smoke test.

A change should not normally be published unless this CI is green.

## PyPI publication

Publication to PyPI is automated with GitHub Actions. Version `0.1.0` validated
this flow end to end.

The workflow is `.github/workflows/release.yml`. It uses no PyPI password and no
long-lived API token: authentication relies on PyPI Trusted Publishing with
OpenID Connect (OIDC). GitHub gives the publish job a short-lived identity that
PyPI verifies before accepting the upload.

## Trusted Publishing configuration

The PyPI project `tabalyst` accepts publications from:

- GitHub owner: `loribel-labs`
- Repository: `tabalyst`
- Workflow: `release.yml`
- Environment: `pypi`

The GitHub repository therefore also has an environment named `pypi`.

These values must match. Renaming the repository, the workflow or the
environment can prevent publication. No PyPI secret is needed in GitHub.

## Triggering a release

The publish workflow runs when a Git tag starting with `v` is pushed to GitHub,
for example `v0.1.0`.

Before publishing, the workflow checks that the tag number exactly matches the
version declared in `pyproject.toml`. A `v0.2.0` tag therefore cannot
accidentally publish a package still declared as `0.1.0`.

The publish job only starts after the build and the previous checks succeed.

## Release flow

```text
development on main
-> local tests
-> commit and push
-> GitHub CI validation
-> version bump if needed
-> matching tag created
-> tag pushed
-> release.yml workflow
-> wheel and sdist build
-> automatic PyPI publication through OIDC
-> available with pip install tabalyst
```

The detailed operating procedure is in `RELEASING.md`.

After publication, check the version from a clean Python environment:

```console
python -m pip install "tabalyst==X.Y.Z"
tabalyst --version
tabalyst report data.csv -o reports/report.html
```

## Safety principle

The release tag is the action that actually triggers a publication. Push it only
after the version and the CI are validated.

A version published on PyPI must never be replaced by a new build with the same
number. To fix something after publication, release a new version, for example
`0.1.1`.

## Key files

- `pyproject.toml`: metadata, version, dependencies and package configuration.
- `src/tabalyst/`: the distributed Python package.
- `.github/workflows/ci.yml`: continuous validation.
- `.github/workflows/release.yml`: PyPI publication.
- `README.md`: user documentation, also shown on PyPI.
- `RELEASING.md`: practical release procedure.
- `docs/dev/packaging-and-release.md`: this page, the packaging and release
  architecture.
