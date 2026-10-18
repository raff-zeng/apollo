#!/usr/bin/env bash
# Copy header trees that only exist inside the Apollo dev container into the
# host-side cache, so host clangd can resolve Apollo's third-party includes.
#
#   /opt/apollo/sysroot/include   boost, osqp, pcl, vtk, opencv, proj, ...
#   /usr/local/include            gflags, glog, gperftools, bvar, ...
#   /usr/local/fast-rtps/include  fastrtps, fastcdr
#
# Run this once after creating the container, or after the container image
# changes. Paths are referenced from .clangd; re-running is cheap when the
# cache is already populated (pass --force to refresh it).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${APOLLO_CONTAINER:-apollo_dev_zrf}"
DEST="${APOLLO_SYSROOT_CACHE:-$ROOT/.cache/apollo-sysroot}"

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
fi

sync_tree() {
  local src="$1" dest="$2" probe="$3"
  if [[ $force -eq 0 && -e "$dest/$probe" ]]; then
    echo "skip $dest (already populated)"
    return
  fi
  rm -rf "$dest"
  mkdir -p "$dest"
  docker cp "$CONTAINER:$src/." "$dest"
  echo "synced $CONTAINER:$src -> $dest"
}

sync_tree /opt/apollo/sysroot/include "$DEST/include" osqp/osqp.h
sync_tree /usr/local/include "$DEST/local-include" third_party/var/bvar/bvar.h
sync_tree /usr/local/fast-rtps/include "$DEST/fast-rtps/include" fastrtps/attributes/PublisherAttributes.h
sync_tree /opt/apollo/absl/include "$DEST/absl/include" absl/strings/str_cat.h
sync_tree /opt/apollo/pkgs/adv_plat "$DEST/pkgs/adv_plat" include/adv_trigger.h
sync_tree /usr/local/cuda-11.8/targets/x86_64-linux/include "$DEST/cuda-11.8/include" cuda_runtime.h
if [[ $force -eq 1 || ! -e "$DEST/cuda-11.8/nvvm/libdevice/libdevice.10.bc" ]]; then
  mkdir -p "$DEST/cuda-11.8/nvvm/libdevice"
  docker cp "$CONTAINER:/usr/local/cuda-11.8/nvvm/libdevice/." "$DEST/cuda-11.8/nvvm/libdevice"
  echo "synced $CONTAINER:/usr/local/cuda-11.8/nvvm/libdevice -> $DEST/cuda-11.8/nvvm/libdevice"
fi
# clang's CUDA detector only accepts a path that also has bin/ and lib64/.
mkdir -p "$DEST/cuda-11.8/bin" "$DEST/cuda-11.8/lib64"

echo "header cache ready at $DEST"
