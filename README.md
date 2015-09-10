# dokuwikifuse
A FUSE filesystem interface to dokuwiki systems.

This is a Python3 only library, which should work with Python 3.3 an higher.

## Ubuntu dependencies
Generic:
```bash
sudo apt-get install python3 python3-dev libattr1-dev libfuse-dev
```

## Limitations
- Only directories that contain a file directly will be shown.
- File writes are not saved to the server (yet).
- Files and directories are only synced from the server once.

## Goals
- [x] Read support
- [x] Login support
- [ ] Write support
- [ ] File and directory syncing after initial sync
- [ ] Creating of documents
- [ ] Removing of documents
- [ ] Renaming of directories
- [ ] Attachement support
