#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
destination=${KNOWLEDGE_BUNDLE_DESTINATION:-"$root/swiftKnowledgeBase"}
checksum=${KNOWLEDGE_BUNDLE_SHA256:-}
url=${KNOWLEDGE_BUNDLE_URL:-}
local_path=${KNOWLEDGE_BUNDLE_PATH:-}

if [ -z "$checksum" ] || ! printf '%s' "$checksum" | grep -Eq '^[0-9a-fA-F]{64}$'; then
  echo "KNOWLEDGE_BUNDLE_SHA256 must be the approved 64-character SHA-256." >&2
  exit 2
fi
if [ -n "$url" ] && [ -n "$local_path" ]; then
  echo "Set exactly one of KNOWLEDGE_BUNDLE_URL or KNOWLEDGE_BUNDLE_PATH." >&2
  exit 2
fi
if [ -z "$url" ] && [ -z "$local_path" ]; then
  echo "Set KNOWLEDGE_BUNDLE_URL or KNOWLEDGE_BUNDLE_PATH." >&2
  exit 2
fi

work=$(mktemp -d "${TMPDIR:-/tmp}/swift-knowledge.XXXXXX")
trap 'rm -rf "$work"' EXIT INT TERM
archive="$work/bundle"

file_checksum() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

checksum_matches() {
  actual=$(file_checksum "$1")
  [ "$(printf '%s' "$actual" | tr 'A-F' 'a-f')" = "$(printf '%s' "$checksum" | tr 'A-F' 'a-f')" ]
}

if [ -n "$url" ]; then
  case "$url" in
    https://*) ;;
    *) echo "Knowledge bundle URLs must use HTTPS." >&2; exit 2 ;;
  esac
  cache=${KNOWLEDGE_BUNDLE_CACHE:-"$root/build/knowledge-bundles/$checksum.bundle"}
  case "$cache" in
    /*) ;;
    *) cache="$root/$cache" ;;
  esac
  if [ -L "$cache" ] || [ -L "$cache.part" ]; then
    echo "Knowledge bundle cache paths must not be symlinks." >&2
    exit 2
  fi
  if [ -f "$cache" ] && checksum_matches "$cache"; then
    cp "$cache" "$archive"
  else
    mkdir -p "$(dirname "$cache")"
    if [ -f "$cache" ]; then
      rm -f "$cache"
    fi
    curl --fail --silent --show-error --location --continue-at - \
      --proto '=https' --proto-redir '=https' --output "$cache.part" "$url"
    cp "$cache.part" "$archive"
  fi
else
  case "$local_path" in
    /*) source_path=$local_path ;;
    *) source_path="$root/$local_path" ;;
  esac
  if [ ! -f "$source_path" ] || [ -L "$source_path" ]; then
    echo "KNOWLEDGE_BUNDLE_PATH must name a regular, non-symlink archive." >&2
    exit 2
  fi
  cp "$source_path" "$archive"
fi

if ! checksum_matches "$archive"; then
  if [ -n "$url" ]; then
    rm -f "$cache.part"
  fi
  echo "Knowledge bundle checksum mismatch." >&2
  exit 1
fi
if [ -n "$url" ] && [ -f "$cache.part" ]; then
  mv "$cache.part" "$cache"
fi

python_bin=${PYTHON:-python3}
"$python_bin" "$root/scripts/extract-knowledge-bundle.py" "$archive" "$work/extracted"
mkdir -p "$destination"
cp -R "$work/extracted/." "$destination/"
echo "Verified knowledge bundle installed at $destination"
