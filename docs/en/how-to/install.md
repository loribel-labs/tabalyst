---
title: Install Tabalyst
description: Install Tabalyst from PyPI on Windows, macOS or Linux, check the installation and upgrade to a new version.
---

Tabalyst needs Python 3.11, 3.12, 3.13 or 3.14. It is installed from PyPI with
`pip`:

```console
pip install tabalyst
tabalyst --version
```

The second command prints the installed version, for example `0.2.1`. The
sections below give the recommended steps for each system.

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

3. Install Tabalyst into this environment:

   ```powershell
   .venv\Scripts\python.exe -m pip install tabalyst
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
python -m pip install tabalyst
tabalyst --version
```

To install the `tabalyst` command once for your user account instead, use
[pipx](https://pipx.pypa.io/):

```console
pipx install tabalyst
```

## Upgrade

Run the install command again with `--upgrade`:

```console
python -m pip install --upgrade tabalyst
```

On Windows without an activated environment:

```powershell
.venv\Scripts\python.exe -m pip install --upgrade tabalyst
```

## Troubleshooting

- **`tabalyst` is not recognized**: the environment is not activated, or the
  Python scripts folder is not on your `PATH`. Use `python -m tabalyst` (or
  `.venv\Scripts\python.exe -m tabalyst` on Windows): `python -m tabalyst`
  accepts the same commands as `tabalyst`.
- **`py` is not recognized on Windows**: Python is not installed, or was
  installed without the launcher. Reinstall it from python.org.
- **Unsupported Python version**: `pip` refuses to install Tabalyst on Python
  3.10 or earlier. Install a supported version and recreate the environment.

## Next step

[Create your first report](../tutorials/first-report.md).
