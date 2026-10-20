# DiscShelf v9.1: Debian 13 packaging

The package requires a Debian 13 system (`python3 >= 3.13`). The resulting
`.deb` contains DiscShelf source and the application launcher, **not** Qt or
LibreOffice binaries. APT installs dependencies separately from Debian's
configured package repositories (or predownloaded local packages).

Build from the project's root directory:

```sh
./packaging/build-deb.sh
```

This writes `dist/discshelf_0.9.1-1_all.deb`. The `all` architecture is correct
for Python-only source and desktop assets; the system's Python/Qt binaries
still need to be available for that processor architecture.

To install (Debian 13):

```sh
sudo apt install ./dist/discshelf_0.9.1-1_all.deb
```

To run:

```sh
discshelf
# Or select DiscShelf from your desktop application menu.
# To inspect an ordinary folder:
discshelf ~/Documents
```

To remove:

```sh
sudo apt remove discshelf
```

Contents:

- `/usr/share/discshelf/*.py`: application code
- `/usr/bin/discshelf`: manual-launch command
- `/usr/share/applications/discshelf.desktop`: application-menu entry
- `/usr/share/icons/hicolor/scalable/apps/discshelf.svg`: app icon

No service or autostart entry is installed. The application monitors only
mounted optical media while its window is running. Automatic mounting is
**not** yet implemented. Internet access is not used to read discs, but
installing dependencies with APT may require package downloads. For a fully
offline installer, collect and redistribute all required `.deb` dependencies
using Debian's licensing and package-repository provisions.

If you publish this package beyond personal testing, replace the placeholder
Maintainer address and create appropriate upstream copyright/license metadata.
