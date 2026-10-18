load("@hedron_compile_commands//:refresh_compile_commands.bzl", "refresh_compile_commands")

package(default_visibility = ["//visibility:public"])

# Regenerate compile_commands.json for navigation across planning, control,
# shared libraries, messages, and basic tools:
#   bazel run //tools/clangd:refresh_compile_commands
refresh_compile_commands(
    name = "refresh_compile_commands",
    targets = [
        "//cyber/...",
        "//modules/common/...",
        "//modules/common_msgs/...",
        "//modules/control/...",
        "//modules/planning/...",
        "//modules/tools/...",
    ],
)
