#!/usr/bin/env python3
"""Rewrite hedron's compile_commands.json so host clangd can resolve Bazel paths.

Hedron emits entries relative to the Bazel workspace, with:
  "directory": "/apollo"
  include paths like "bazel-out/k8-fastbuild/bin" and "external/<repo>"

Inside the container /apollo is the workspace, but on the host the workspace is
/home/zrf/apollo and the bazel-out / external symlinks point back into
/apollo/... (they are absolute, so they break outside the container).

This script rewrites the directory to the host workspace and replaces the
bazel-out/ and external/ prefixes with workspace-relative paths into
.cache/bazel/<hash>/. The result works on the host and inside the container.
"""

import json
import os
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <compile_commands.json> <host-workspace>", file=sys.stderr)
        return 2

    db_path, host_ws = sys.argv[1], os.path.abspath(sys.argv[2])
    host_ws = host_ws.rstrip("/")

    # bazel-out is created by Bazel inside the container and points at
    # /apollo/.cache/...; map that back onto the host workspace.
    link = os.path.join(host_ws, "bazel-out")
    if not os.path.islink(link):
        print(f"error: {link} is not a symlink; run a bazel build in the container first", file=sys.stderr)
        return 1
    raw_target = os.readlink(link)
    if raw_target.startswith("/apollo/"):
        bazel_out_host = host_ws + raw_target[len("/apollo"):]
    else:
        bazel_out_host = os.path.join(host_ws, raw_target)
    bazel_out_host = os.path.normpath(bazel_out_host)
    if not os.path.isdir(bazel_out_host):
        print(f"error: cannot resolve {link} -> {bazel_out_host}", file=sys.stderr)
        return 1

    rel_bazel_out = os.path.relpath(bazel_out_host, host_ws)
    rel_external = os.path.relpath(
        os.path.normpath(os.path.join(bazel_out_host, "../../../external")), host_ws
    )

    def fix_path(token: str, prefix: str = "") -> str:
        raw = token[len(prefix):]
        if raw == "/apollo" or raw.startswith("/apollo/"):
            return prefix + host_ws + raw[len("/apollo"):]
        if raw == "bazel-out" or raw.startswith("bazel-out/"):
            return prefix + rel_bazel_out + raw[len("bazel-out"):]
        if raw == "external" or raw.startswith("external/"):
            return prefix + rel_external + raw[len("external"):]
        return token

    with open(db_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    for entry in entries:
        entry["directory"] = host_ws
        args = entry.get("arguments")
        if args is not None:
            fixed = []
            for arg in args:
                # -Ibazel-out/... and friends are single tokens.
                if arg.startswith("-I") and len(arg) > 2:
                    fixed.append(fix_path(arg, "-I"))
                else:
                    fixed.append(fix_path(arg))
            entry["arguments"] = fixed
        elif "command" in entry:
            entry["command"] = " ".join(
                fix_path(tok) for tok in entry["command"].split()
            )

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, separators=(",", ":"))

    print(f"rewrote {len(entries)} entries: directory={host_ws}")
    print(f"  bazel-out -> {rel_bazel_out}")
    print(f"  external  -> {rel_external}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
