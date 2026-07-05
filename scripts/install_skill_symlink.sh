#!/usr/bin/env bash
# Install one skill by symlink only. Never copy a skill directory onto an
# existing skill symlink: on macOS `cp -R src dest` follows `dest` when it is a
# symlinked directory and creates src/basename(src), dirtying the source repo.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <source-skill-dir> <destination-skills-dir>" >&2
  exit 2
fi

src="$1"
dest_root="$2"

if [ ! -d "$src" ] || [ ! -f "$src/SKILL.md" ]; then
  echo "install-skill: source is not a skill dir: $src" >&2
  exit 1
fi

src_real="$(cd "$src" && pwd -P)"
name="$(basename "$src_real")"
dest="$dest_root/$name"

mkdir -p "$dest_root"

if [ -L "$dest" ]; then
  current="$(readlink "$dest")"
  case "$current" in
    /*) current_path="$current" ;;
    *) current_path="$(dirname "$dest")/$current" ;;
  esac
  if [ -e "$dest" ]; then
    current_real="$(cd "$current_path" && pwd -P)"
    if [ "$current_real" = "$src_real" ]; then
      echo "install-skill: already linked $dest -> $src_real"
      exit 0
    fi
  fi
  echo "install-skill: refusing to replace existing symlink: $dest -> $current" >&2
  exit 1
fi

if [ -e "$dest" ]; then
  echo "install-skill: refusing to overwrite existing path: $dest" >&2
  exit 1
fi

ln -s "$src_real" "$dest"
echo "install-skill: linked $dest -> $src_real"
