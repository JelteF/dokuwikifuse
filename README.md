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

## Installation
This installation is done using `virtualenv`, it is the most easy way.
```bash
git clone https://github.com/JelteF/dokuwikifuse
cd dokuwikifuse
virtualenv venv -p python3
. venv/bin/activate
pip install -r requirements.txt
```

You can create your own `config.py` which overrides the default values like
this:

```python
from default_config import DefaultConfig


class Config(DefaultConfig):
    user = 'john'
    password = 'secretpassword'
```

For all the config options see `default_config.py`

## Usage
To mount:
```bash
venv/bin/python dokuwikifuse.py
```
To unmount:
```
fusermount -u wiki
```

## Limitations
- Only directories that contain a file directly will be shown.
- Every filewrite is sent to the server directly, which means multiple revisions
    can exists for one change to a large file, since multiple writes occur.
- Files and directories are only synced from the server once.

## Goals
- [x] Read support
- [x] Login support
- [x] Write support
- [ ] Submit only once when consecutive writes occur
- [ ] File and directory syncing after initial sync
- [x] Creating of documents
- [x] Removing of documents
- [ ] Renaming of directories
- [ ] Attachement support
