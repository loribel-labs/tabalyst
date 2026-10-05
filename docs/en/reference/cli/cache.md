---
title: "CLI: tabalyst cache"
description: The tabalyst cache info and tabalyst cache clean commands, which show and remove the disposable query caches of Tabalyst projects.
---

```console
tabalyst cache info [SOURCE]
tabalyst cache clean [SOURCE]
```

`info` shows the number and size of the disposable query caches of Tabalyst
projects, and `clean` removes them. A cache never holds anything that cannot be
rebuilt, and `clean` never removes a scan or a database. See [Manage query
caches](../../scan/cache.md).

## Arguments and options

| Argument | Description |
| --- | --- |
| `SOURCE` | Optional CSV file whose project is selected. Without it, every project is |
| `--help` | Show the options and exit |

`cache` has no other options and takes no glob pattern.

## Examples

```console
tabalyst cache info
tabalyst cache info customers.csv
tabalyst cache clean
tabalyst cache clean customers.csv
```

```text
Cache: 0 directories in 0 projects (0 bytes).
Cleaned 0 cache directories in 0 projects (0 bytes).
```

## Exit codes

| Code | When |
| --- | --- |
| `0` | Success, even when nothing was found to remove |
| `4` | The source file named in the command has no Tabalyst project |
