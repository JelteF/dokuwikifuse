# dokuwikifuse
A FUSE filesystem interface to dokuwiki systems.

This is a Python3 only library, which should work with Python 3.3 an higher.

This is very much **ALPHA** software, see the limitations section for details on
issues that currently exist.


## Ubuntu dependencies
Generic:
```bash
sudo apt-get install python3 python3-dev libattr1-dev libfuse-dev
```

## Limitations
- Only directories that contain a file directly will be shown.
- Every filewrite is sent to the server directly, which means multiple revisions
    can exists for one change to a large file, since multiple writes occur.
- Files and directories are only synced from the server once.

## Goals
- [x] Read support
- [x] Login support
- [x] Write upport
- [ ] Writing
- [ ] File and directory syncing after initial sync
- [ ] Creating of documents
- [ ] Removing of documents
- [ ] Renaming of directories
- [ ] Attachement support
