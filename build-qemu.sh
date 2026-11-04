#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
archive=${QEMU_TARBALL:-"$root/work/qemu-11.1.2.tar.xz"}
src="$root/work/qemu-src"
build="$src/build-a7m3"
overlay="$root/source/qemu"

# Only local archives are used; configure and Meson must never fetch dependencies.
printf '%s  %s\n' 731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016 "$archive" | sha256sum --check --status
printf '%s  %s\n' c1fb23f4f39fc88da4a1f89b06ea13e8683de886ee77dbb99369f8763dfe809e "$overlay/dtc-b6910bec.tar.xz" | sha256sum --check --status
if [[ -L "$src" || -L "$build" ]]; then
    echo 'Refusing a symlinked QEMU source/build directory.' >&2
    exit 1
fi
if [[ ! -f "$src/configure" ]]; then
    mkdir -p "$src"
    if [[ -n "$(ls -A -- "$src")" ]]; then
        echo "Incomplete source directory: $src (preserved; move it aside before retrying)." >&2
        exit 1
    fi
    tar -xJf "$archive" --strip-components=1 -C "$src"
fi
[[ $(<"$src/VERSION") == 11.1.2 ]]
if [[ ! -f "$src/subprojects/dtc/meson.build" ]]; then
    tar -xJf "$overlay/dtc-b6910bec.tar.xz" -C "$src/subprojects"
fi

cd "$src"
registration="$overlay/0001-register-a7m3.patch"
if patch --batch --fuzz=0 --forward -p1 --dry-run < "$registration" >/dev/null 2>&1; then
    patch --batch --fuzz=0 --forward -p1 < "$registration"
elif ! patch --batch --fuzz=0 --reverse -p1 --dry-run < "$registration" >/dev/null 2>&1; then
    echo 'QEMU registration differs from the supplied patch; existing files preserved.' >&2
    exit 1
fi
for file in hw/arm/a7m3.c hw/arm/a7m3-gpe-init.h hw/timer/sony_hwtimer.c; do
    if ! cmp -s "$overlay/$file" "$src/$file"; then
        install -m 644 "$overlay/$file" "$src/$file"
    fi
done

mkdir -p "$build"
cd "$build"
../configure --target-list=arm-softmmu --disable-download \
    --without-default-features --enable-tcg --enable-fdt=internal \
    --enable-pixman --enable-sdl --disable-werror \
    --disable-tools --disable-guest-agent --disable-docs \
    2>&1 | tee configure.log
ninja -j8 qemu-system-arm 2>&1 | tee build.log

# Realize the board with no guest network or disks, inspect devices, then QMP quit.
python3 - "$build/qemu-system-arm" "$build" <<'PY'
import json
import pathlib
import subprocess
import sys

binary, output = sys.argv[1], pathlib.Path(sys.argv[2])
commands = [
    {"execute": "qmp_capabilities", "id": "capabilities"},
    {"execute": "qom-get", "arguments": {"path": "/machine", "property": "type"}, "id": "type"},
    {"execute": "query-machines", "id": "machines"},
    {"execute": "query-status", "id": "status"},
    {"execute": "query-cpus-fast", "id": "cpus"},
    {"execute": "query-block", "id": "disks"},
    {"execute": "query-rx-filter", "id": "network"},
    {"execute": "human-monitor-command", "arguments": {"command-line": "info qtree"}, "id": "devices"},
    {"execute": "human-monitor-command", "arguments": {"command-line": "info mtree"}, "id": "memory"},
    {"execute": "quit", "id": "quit"},
]
result = subprocess.run(
    [binary, "-M", "a7m3", "-cpu", "cortex-a9", "-smp", "1", "-m", "1024",
     "-S", "-nodefaults", "-display", "none", "-serial", "none", "-monitor", "none",
     "-nic", "none", "-qmp", "stdio"],
    input="".join(json.dumps(command) + "\n" for command in commands),
    text=True, capture_output=True, timeout=30,
)
(output / "verification-qmp.log").write_text(result.stdout)
(output / "verification-stderr.log").write_text(result.stderr)
assert result.returncode == 0, (result.returncode, result.stderr)
messages = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
responses = {message["id"]: message for message in messages if "id" in message}
for command in commands:
    assert "return" in responses.get(command["id"], {}), responses.get(command["id"])
values = {key: response["return"] for key, response in responses.items()}
assert values["type"] == "a7m3-machine", values["type"]
assert any(machine["name"] == "a7m3" for machine in values["machines"])
assert not any("zve10" in machine["name"].lower() for machine in values["machines"])
assert values["status"]["running"] is False, values["status"]
assert len(values["cpus"]) == 1, values["cpus"]
assert values["disks"] == [] and values["network"] == [], (values["disks"], values["network"])
assert values["devices"].count("dev: sony-hwtimer,") == 9, values["devices"]
assert "dev: pl181," in values["devices"], values["devices"]
assert "dev: pl011," in values["devices"], values["devices"]
assert "a7m3-gpe" in values["memory"] and "a7m3-sugi" in values["memory"]
version = subprocess.check_output([binary, "--version"], text=True).splitlines()[0]
report = {"version": version, "machine": values["type"], "cpus": 1,
          "sony_timers": 9, "pl181": True, "pl011": True,
          "guest_disks": [], "guest_network": [], "qmp_quit_exit_code": result.returncode,
          "firmware_boot_verified": False, "physical_asic_compatibility_verified": False}
(output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY
sha256sum qemu-system-arm | tee qemu-system-arm.sha256
printf 'QEMU ready: %s\n' "$build/qemu-system-arm"
