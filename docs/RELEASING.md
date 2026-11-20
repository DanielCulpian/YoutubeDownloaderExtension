# GitHub release checklist

## Source preparation

1. Run the documented Python and JavaScript test suites.
2. Run installer preparation with `-PrepareOnly -SkipDependencies` and inspect
   the generated native manifest, extension ID, and registration plan.
3. Follow the manual acceptance matrix for browsers you intend to call verified.
4. Check that function summaries, source comments, and documentation are in English.
   The current user interface may remain in Spanish.
5. Keep `LICENSE`, `DISCLAIMER.md`, and third-party notices with the source.

## Exclude generated and personal data

Do not upload `.venv`, `.runtime`, caches, media, logs, or local test outputs.
Runtime manifests contain absolute local paths; preferences and logs can expose
video URLs and destinations. `.gitignore` excludes these files, but review the
actual staged list before every commit:

```powershell
git status --short
git diff --cached --stat
git ls-files
```

Adding a path to `.gitignore` does not remove a previously tracked file. If this
is an existing repository, inspect its tracked files and history before publishing.
Never commit downloaded third-party media, private credentials, or dependency binaries.

## Versioning and publication

Update `extension-vivaldi/extension/manifest.json` when releasing a new extension
version. Keep its public key unless intentionally changing the extension identity.
Document user-visible changes and required migration steps. Browser-store
publication is separate from publishing source on GitHub and can have additional
policies and identity requirements.

This preparation does not create a GitHub repository, push a commit, publish a
release, or register the extension in a browser store. Perform those actions only
when intentionally releasing the reviewed source.
