# Soft-delete convention

The project root in this workspace sits on a FUSE mount that refuses `unlink` but permits `rename`. `rm` fails with `Operation not permitted` even under `dangerouslyDisableSandbox`; `mv` works. This note captures the working convention so agents don't rediscover it each session.

## The rule

Never `rm` a file. Move it instead:

```
mkdir -p .to_delete
mv <file> .to_delete/<tag>-$(date +%Y%m%d-%H%M%S)
```

`<tag>` is a short human-readable hint about what the file was (e.g. `index-lock`, `stale-fixture`, `aborted-scratch`). The timestamp makes the filename unique even if the same kind of file gets soft-deleted twice in a session.

## Why a folder instead of a `.gitkeep` stub

`.to_delete/` is not tracked. Agents create it on demand. Tom empties it periodically from Windows via select-all-delete in File Explorer, which is more convenient without a stub file inside fighting the select-all. Do not add `.to_delete/` to `.gitignore` unless it starts getting auto-created during CI — so far it doesn't.

## Cosmetic unlink warnings

A successful git commit will often print:

```
warning: unable to unlink '.git/index.lock': Operation not permitted
```

This warning is cosmetic. The commit landed. Check `git log -1` and move on — do not retry, do not try to clean up the lock.

## Stale lock recovery

If a git command fails with `fatal: Unable to create '.git/index.lock': File exists` (usually left behind by an earlier interrupted git op), soft-delete the lock and retry:

```
mv .git/index.lock .to_delete/index-lock-$(date +%Y%m%d-%H%M%S)
```

Same pattern for `.git/HEAD.lock` or any other stale `*.lock` under `.git/`.

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
