---
title: Manage query caches
description: Inspect and clean the disposable query caches of Tabalyst DuckDB projects with tabalyst cache info and tabalyst cache clean.
---

`tabalyst cache` shows how much disk space the disposable query caches of your
Tabalyst projects use, and removes them. A cache never holds anything that
cannot be rebuilt.

```console
tabalyst cache info
tabalyst cache clean
```

```text
Cache: 0 directories in 0 projects (0 bytes).
Cleaned 0 cache directories in 0 projects (0 bytes).
```

## What a cache is

A **project** is the storage Tabalyst keeps for one source file in its local
storage directory (`workspaces/local/projects/`, under `TABALYST_HOME` when
that variable is set). A DuckDB project holds a scan and a database. Its
**query caches** are directories of intermediate query results that speed up
later reads of the database.

In 0.5.0, the commands `tabalyst scan` and `tabalyst report` store a plain
`scan.json` and do not build a DuckDB database. They create no query cache,
so `tabalyst cache` reports 0 directories unless projects built by 0.4.3 exist
on your computer. Those projects are left untouched by other commands.

## Show the size of the caches

```console
tabalyst cache info
tabalyst cache info customers.csv
```

Without an argument, `info` covers every project. With a CSV file, it covers
the project of that source and fails with an error when the source has no
project. It prints the number of managed cache directories, the number of
projects and their logical size, followed by `Retained:` lines for entries
Tabalyst cannot manage and therefore never removes.

## Clean the caches

```console
tabalyst cache clean
tabalyst cache clean customers.csv
```

`clean` removes only the cache directories that Tabalyst owns. It never
removes the scan or the database of a project, and it does not modify your
source files. A project that is being read is skipped, with a warning on
standard error; run the command again once the reader has closed.

The summary goes to standard error, so `tabalyst cache clean 2>$null` hides it
in PowerShell.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, even when nothing was found to remove |
| `4` | The source file named in the command has no Tabalyst project |

See [Command line reference](../reference/cli.md) for all commands.
