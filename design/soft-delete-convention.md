# Soft-delete convention

The project root in this workspace sits on a FUSE mount that refuses `unlink` but permits `rename`. `rm` fails with `Operation not permitted` even under `dangerouslyDisableSandbox`; `mv` works. This note captures the working convention so agents don't rediscover it each session.

## The rule

Never `rm` a file. Move it instead:

```
mkdir -p .to_delete
mv <file> .to_delete/<tag>-$(date +%Y%m%d-%H%M%S)
```

`<tag>` is a short human-readable hint about what the file was (e.g. `index-lock`, `stale-fixture`, `aborted-scratch`). The timestamp makes the filename unique even if the same kind of file gets soft-deleted twice in a session.

## Pre-op lock sweep (applies to every git command)

This mount leaves git's internal lock files behind after *every* successful operation — git's attempt to remove them via `unlink` fails with `Operation not permitted` (the warnings are cosmetic; see below), and the leftover locks block the *next* git command with `fatal: Unable to create '.git/index.lock': File exists` or `fatal: cannot lock ref 'HEAD': Unable to create '.git/HEAD.lock'`. Treat lock cleanup as a preflight step, not an emergency recovery.

Before any git command in a session:

```
mkdir -p .to_delete
TS=$(date +%Y%m%d-%H%M%S)
for lock in $(find .git -name "*.lock" -type f); do
  mv "$lock" ".to_delete/$(basename "$lock")-$TS"
done
```

The sweep is cheap (a handful of files at most), idempotent (no lock = no move), and catches every `.lock` under `.git/` in one shot. Observed lock paths on this mount: `.git/index.lock` (left by `git add`, `git commit`), `.git/HEAD.lock` (left by `git commit` on HEAD update), `.git/objects/maintenance.lock` (left by git's background maintenance checks triggered by routine ops).

Chaining the sweep into the same bash call as the git command keeps the preflight visible in the transcript and avoids forgetting it:

```
mkdir -p .to_delete && TS=$(date +%Y%m%d-%H%M%S) \
  && for lock in $(find .git -name "*.lock" -type f); do mv "$lock" ".to_delete/$(basename "$lock")-$TS"; done \
  && git commit -m "..."
```

**Related but separate:** `.git/objects/*/tmp_obj_*` files also accumulate (same `unlink` refusal on git's write-temp files). These aren't `.lock` files and don't block future commands, so they're ignored by the sweep above. If accumulation ever becomes a nuisance, sweep them with a `find .git/objects -name "tmp_obj_*" -exec mv ... \;` pattern — otherwise leave them alone.

## Why a folder instead of a `.gitkeep` stub

`.to_delete/` is not tracked. Agents create it on demand. Tom empties it periodically from Windows via select-all-delete in File Explorer, which is more convenient without a stub file inside fighting the select-all. Do not add `.to_delete/` to `.gitignore` unless it starts getting auto-created during CI — so far it doesn't.

## Cosmetic unlink warnings

A successful git commit will often print:

```
warning: unable to unlink '.git/index.lock': Operation not permitted
```

This warning is cosmetic. The commit landed. Check `git log -1` and move on — do not retry. The leftover lock will be cleared by the next git op's preflight sweep (see "Pre-op lock sweep" above).

## Corrupt index recovery

If `git status` or `git add` fails with `fatal: index file corrupt` or `fatal: Unable to read index`, the index itself needs to be rebuilt:

```
mv .git/index .to_delete/index-$(date +%Y%m%d-%H%M%S)
git reset
```

`git reset` (no args, no `--hard`) rebuilds the index from HEAD. The working tree is untouched, so no staged work is lost beyond the staging state itself — reapply `git add` on the files you actually want in the next commit.

## When not to use soft-delete

- **Scratch files inside the sandbox working dir (`/sessions/keen-sleepy-goodall/`, not the mount).** Those live on a real filesystem that accepts `rm`.
- **Ephemeral output that doesn't need to persist even as a renamed artifact.** If you want a file truly gone and it's outside the mount, just `rm` it.

The soft-delete convention is specifically about keeping the mount cooperative; don't over-apply it.
