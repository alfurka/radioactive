# Radioactive

<p align="center">
	<img src="./art/logo.png" alt="Radioactive cursors logo">
</p>

Simple cursor theme for the lovers of radioactivity, now with SVG cursors that
work on **GNOME 51**.

This is a fork of [alvatip/radioactive](https://github.com/alvatip/radioactive).
The original Xcursor bitmaps are not supported by GNOME 51, so every cursor has
been re-created as a scalable SVG, traced from the original artwork. The classic
Xcursor files are still included for X11 and older desktops.

## Preview

The scalable cursors on a dark and a light background:

![Radioactive SVG cursors](./art/preview-svg.png)

### Busy cursors

The `progress` cursor (arrow with a small spinning radioactive symbol) and the
`wait` cursor (the big spinning radioactive symbol) are the original animations,
traced frame by frame.

![Busy cursors: progress and wait](./art/busy-cursors.gif)

The original bitmap cursors are shown in [art/preview.png](./art/preview.png).

## Installation

The installer detects whether it is run as a regular user or as root. For a
user-only installation, run:

```sh
./install.sh
```

For a system-wide installation, run:

```sh
sudo ./install.sh
```

The package includes the classic Xcursor files and native vector artwork in
`cursors_scalable` for GNOME 51 and other desktops that load SVG cursor themes.
The SVGs are traced from the original 96px cursor artwork, so they look like the
originals at any size or display density, and they keep the Xcursor hotspots.

To rebuild the SVG cursors, run `python3 build-scalable-cursors.py` from the
repository root. It needs Pillow, NumPy and the `potrace` command line tool.

### Archive installation

The archive contains a top-level `Radioactive/` directory. For a user-only
installation, extract it into the local icon directory:

```sh
mkdir -p "$HOME/.local/share/icons"
tar -xzf archives/Radioactive.tar.gz -C "$HOME/.local/share/icons"
```

For a system-wide installation, use `/usr/share/icons` as the destination.

After installing, select **Radioactive** in GNOME Tweaks or run:

```sh
gsettings set org.gnome.desktop.interface cursor-theme 'Radioactive'
```

If the cursor does not update immediately, log out and back in.

## Also available on Pling

[Radioactive on Pling](https://www.pling.com/p/1579027/)

## Uninstallation

Remove `Radioactive` from the directory where it was installed:

```sh
rm -r "$HOME/.local/share/icons/Radioactive"
```

For a system-wide installation, remove `/usr/share/icons/Radioactive` with
administrator privileges.

## From the same author

- [Nordzy icon theme](https://github.com/alvatip/Nordzy-icon)
- [Nordzy-cursors](https://github.com/alvatip/Nordzy-cursors)

## Licence

GNU General Public Licence v3.0. See [COPYING](./COPYING).
