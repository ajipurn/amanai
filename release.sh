#!/usr/bin/env sh
# Cut a release: bump VERSION, sync generated version references, commit, tag,
# push. The tag push triggers .github/workflows/release.yml (PyPI) and
# release-node.yml (npm) -- one tag, both ecosystems, same version.
set -eu

BUMP="patch"
DRY_RUN=0
SKIP_TESTS="${AMANAI_RELEASE_SKIP_TESTS:-0}"
REMOTE="${AMANAI_RELEASE_REMOTE:-origin}"
BRANCH="${AMANAI_RELEASE_BRANCH:-main}"

# Single source of truth for the version. sync-version.mjs fans it out to the
# Python SDK, Node SDK, lockfile, and README badge.
VERSION_FILE="VERSION"
NODE_DIR="packages/sdk-node"
SYNC_SCRIPT="scripts/sync-version.mjs"

info() {
  printf '%s\n' "$1"
}

fail() {
  printf 'amanai release: %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  ./release.sh --patch     # 0.1.0 -> 0.1.1  (default)
  ./release.sh --minor     # 0.1.0 -> 0.2.0
  ./release.sh --major     # 0.1.0 -> 1.0.0
  ./release.sh --dry-run   # print what would happen, change nothing

Env:
  AMANAI_RELEASE_SKIP_TESTS=1   skip ruff + pytest gate
  AMANAI_RELEASE_REMOTE=origin  git remote to push to
  AMANAI_RELEASE_BRANCH=main    branch that release runs on
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --patch) BUMP="patch" ;;
    --minor) BUMP="minor" ;;
    --major) BUMP="major" ;;
    --dry-run) DRY_RUN=1 ;;
    -h | --help) usage; exit 0 ;;
    *) usage; fail "unknown option: $1" ;;
  esac
  shift
done

# Run from the repo root regardless of where the script is invoked from.
CDPATH= cd -- "$(dirname -- "$0")"

command -v git >/dev/null 2>&1 || fail "git not found"
command -v node >/dev/null 2>&1 || fail "node not found (needed to sync versions)"
[ -f "$VERSION_FILE" ] || fail "version file not found: $VERSION_FILE"
[ -f "$SYNC_SCRIPT" ] || fail "version sync script not found: $SYNC_SCRIPT"
[ -f "$NODE_DIR/package.json" ] || fail "node package.json not found: $NODE_DIR/package.json"

# Preconditions: right branch, nothing uncommitted (the bump must be the only change).
branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "$BRANCH" ] || fail "on branch '$branch', expected '$BRANCH'"
[ -z "$(git status --porcelain)" ] || fail "working tree not clean — commit or stash first"

# Read current version, compute the next one.
current="$(tr -d '[:space:]' < "$VERSION_FILE")"
printf '%s\n' "$current" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' \
  || fail "could not read x.y.z version from $VERSION_FILE"

major="${current%%.*}"
rest="${current#*.}"
minor="${rest%%.*}"
patch="${rest##*.}"

case "$BUMP" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
esac
new="$major.$minor.$patch"
tag="v$new"

git rev-parse "$tag" >/dev/null 2>&1 && fail "tag $tag already exists"

info "release: $current -> $new  (tag $tag, push to $REMOTE/$BRANCH — PyPI + npm)"

if [ "$DRY_RUN" = "1" ]; then
  info "[dry-run] no files changed, nothing pushed"
  exit 0
fi

if [ "$SKIP_TESTS" = "0" ]; then
  info "running ruff + pytest..."
  uvx ruff@0.8.4 check . || fail "lint failed"
  uvx --python 3.10 --with pytest pytest || fail "tests failed"
fi

printf '%s\n' "$new" > "$VERSION_FILE"
node "$SYNC_SCRIPT" || fail "version sync failed"
node "$SYNC_SCRIPT" --check || fail "version sync check failed"

git add "$VERSION_FILE" "$SYNC_SCRIPT" README.md packages/sdk-python/amanai/__init__.py "$NODE_DIR/package.json"
[ -f "$NODE_DIR/package-lock.json" ] && git add "$NODE_DIR/package-lock.json"
git commit -m "release: $tag"
git tag -a "$tag" -m "$tag"
git push "$REMOTE" "$BRANCH"
git push "$REMOTE" "$tag"

info "pushed $tag — watch the Publish workflows: PyPI (release.yml) + npm (release-node.yml)"
