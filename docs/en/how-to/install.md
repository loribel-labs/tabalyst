---
title: Install Tabalyst
description: Install or update Tabalyst from PyPI on Windows, macOS or Linux, and keep it up to date before each test.
---

Tabalyst needs Python 3.11, 3.12, 3.13 or 3.14. The same command installs it
from PyPI, or updates it when it is already installed:

```console
pip install --upgrade tabalyst
tabalyst --version
```

The second command prints the installed version, for example `0.2.1`.

> **Update before each test.** Tabalyst is in alpha and new versions are
> released often, with fixes and new options. Run
> `pip install --upgrade tabalyst` before testing, before following a tutorial
> and before reporting a problem. See
> [Keep Tabalyst up to date](#keep-tabalyst-up-to-date).

The sections below give the recommended steps for each system.

## Windows

1. Install Python 3.11 or later from [python.org](https://www.python.org/downloads/)
   or the Microsoft Store. Then open a new PowerShell window and check the
   version:

   ```powershell
   py --version
   ```

2. Create a virtual environment in your working folder. It keeps Tabalyst
   separate from other Python projects:

   ```powershell
   py -m venv .venv
   ```

3. Install Tabalyst into this environment. The same command updates it later:

   ```powershell
   .venv\Scripts\python.exe -m pip install --upgrade tabalyst
   ```

4. Check the installation:

   ```powershell
   .venv\Scripts\python.exe -m tabalyst --version
   ```

To type `tabalyst` directly, activate the environment first in each new
PowerShell window:

```powershell
.venv\Scripts\Activate.ps1
tabalyst --version
```

If PowerShell refuses to run `Activate.ps1` because script execution is
disabled, keep using `.venv\Scripts\python.exe -m tabalyst` instead: it accepts
exactly the same commands.

## macOS and Linux

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade tabalyst
tabalyst --version
```

To install the `tabalyst` command once for your user account instead, use
[pipx](https://pipx.pypa.io/):

```console
pipx install tabalyst
```

With pipx, update with `pipx upgrade tabalyst`.

## Keep Tabalyst up to date

Tabalyst changes often during its alpha. Update it before each test session,
before following this documentation and before reporting a problem: the
documentation describes the latest release, and older versions may lack
commands or options.

```console
python -m pip install --upgrade tabalyst
tabalyst --version
```

On Windows without an activated environment:

```powershell
.venv\Scripts\python.exe -m pip install --upgrade tabalyst
.venv\Scripts\python.exe -m tabalyst --version
```

Compare the printed version with the latest release on
[PyPI](https://pypi.org/project/tabalyst/). Updating keeps your reports and
configuration files: it only replaces the installed package.

## Troubleshooting

- **`tabalyst` is not recognized**: the environment is not activated, or the
  Python scripts folder is not on your `PATH`. Use `python -m tabalyst` (or
  `.venv\Scripts\python.exe -m tabalyst` on Windows): `python -m tabalyst`
  accepts the same commands as `tabalyst`.
- **`py` is not recognized on Windows**: Python is not installed, or was
  installed without the launcher. Reinstall it from python.org.
- **A command or option from this documentation is missing**: your version is
  older than the documented one. Update Tabalyst, then check
  `tabalyst --version`.
- **Unsupported Python version**: `pip` refuses to install Tabalyst on Python
  3.10 or earlier. Install a supported version and recreate the environment.

## Next step

[Create your first report](../tutorials/first-report.md).
