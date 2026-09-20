# Releasing Tabalyst

Production releases are built by GitHub Actions and published to PyPI through
Trusted Publishing. Do not create the release tag until Gregory has explicitly
approved publication.

## One-time configuration

1. Secure the PyPI account with strong authentication.
2. Create a PyPI Trusted Publisher (or pending publisher) with:
   - GitHub owner: `loribel-labs`
   - Repository: `tabalyst`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. Create the `pypi` GitHub Environment and add Gregory as a required reviewer.

No PyPI token or password belongs in GitHub secrets.

## Release checklist

1. Set the version once in `pyproject.toml` and update release notes.
2. Run:

   ```console
   python -m pytest
   python -m ruff check .
   python -m build
   ```

3. Create a fresh virtual environment outside the repository, install the wheel
   from `dist/`, and verify the Python API and installed `tabalyst` command both
   create HTML, JSON, and `executions.json` artifacts.
4. Inspect the wheel contents and a generated HTML report to confirm the template,
   CSS, and JavaScript are included.
5. Merge the prepared release commit and wait for CI to pass.
6. After explicit publication approval, create and push the matching tag, for
   example `v0.1.0` for package version `0.1.0`.
7. Approve the protected `pypi` environment deployment when GitHub requests it.
8. Verify the package page and install the published wheel in another clean
   environment.

The release workflow rejects any tag that does not exactly match the version in
`pyproject.toml`. Its build job has read-only repository permissions; only the
separate publish job receives `id-token: write`.
