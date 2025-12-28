#!/usr/bin/env bash
# mb-scan-bundle.sh
#
# Creates ONE JSON bundle (scan_bundle.json by default) containing 7 hardware datapoints:
#   - lshw   (native JSON)
#   - lsblk  (native JSON)
#   - lspci  (text)
#   - lsusb  (text)
#   - upower (text)
#   - edid   (text, decoded from /sys/class/drm/*/edid via edid-decode)
#   - smart  (text, smartctl -i -H -A for all NON-USB disks)
#
# "Forgiving" behavior:
#   - Missing tools or command failures do NOT stop the script.
#   - Any failed/missing source becomes null in sources.<name>.
#   - rc + stderr for each source is stored in meta.status.<name>.
#
# Usage:
#   sudo ./mb-scan-bundle.sh                # writes ./scan_bundle.json
#   sudo ./mb-scan-bundle.sh out.json       # writes ./out.json
#
# Requirements:
#   - bash, jq
#   - lshw, lsblk, lspci, lsusb, upower (recommended)
#   - edid-decode (optional)
#   - smartctl (optional)

set -u

OUT="${1:-scan_bundle.json}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

run_cmd() {
  # run_cmd <name> <command...>
  name="$1"; shift
  "$@" >"$tmp/$name.out" 2>"$tmp/$name.err" || true
  echo $? >"$tmp/$name.rc"
}

# 1) native JSON sources
run_cmd lshw  lshw -json
run_cmd lsblk lsblk -J -b -O

# 2) text sources
run_cmd lspci  lspci -vmm -nn -k
run_cmd lsusb  lsusb
run_cmd upower upower -d

# 3) edid: decode all DRM EDID blobs (internal panel, etc.)
: >"$tmp/edid.out"; : >"$tmp/edid.err"; edid_rc=0
if command -v edid-decode >/dev/null 2>&1; then
  shopt -s nullglob
  found=0
  for p in /sys/class/drm/*/edid; do
    [ -s "$p" ] || continue
    found=1
    printf '===== %s =====\n' "$p" >>"$tmp/edid.out"
    if ! edid-decode "$p" >>"$tmp/edid.out" 2>>"$tmp/edid.err"; then
      edid_rc=1
    fi
    printf '\n' >>"$tmp/edid.out"
  done
  [ "$found" -eq 1 ] || edid_rc=1
else
  echo "edid-decode not found" >"$tmp/edid.err"
  edid_rc=127
fi
echo "$edid_rc" >"$tmp/edid.rc"

# 4) smart: smartctl for all NON-USB disks
: >"$tmp/smart.out"; : >"$tmp/smart.err"; smart_rc=0
if command -v smartctl >/dev/null 2>&1; then
  found=0
  while read -r name type tran; do
    [ "$type" = "disk" ] || continue
    [ "${tran:-}" = "usb" ] && continue
    found=1
    dev="/dev/$name"
    printf '===== %s =====\n' "$dev" >>"$tmp/smart.out"
    if ! smartctl -i -H -A "$dev" >>"$tmp/smart.out" 2>>"$tmp/smart.err"; then
      smart_rc=1
    fi
    printf '\n' >>"$tmp/smart.out"
  done < <(lsblk -dn -o NAME,TYPE,TRAN)
  [ "$found" -eq 1 ] || smart_rc=1
else
  echo "smartctl not found" >"$tmp/smart.err"
  smart_rc=127
fi
echo "$smart_rc" >"$tmp/smart.rc"

# 5) one jq call: build the final bundle JSON
jq -n \
  --arg schema "motherboard.scan_bundle.v1" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg hostname "$(hostname)" \
  --arg user "${SUDO_USER:-$USER}" \
  --rawfile lshw_raw  "$tmp/lshw.out"  --arg lshw_rc  "$(cat "$tmp/lshw.rc")"  --rawfile lshw_err  "$tmp/lshw.err" \
  --rawfile lsblk_raw "$tmp/lsblk.out" --arg lsblk_rc "$(cat "$tmp/lsblk.rc")" --rawfile lsblk_err "$tmp/lsblk.err" \
  --rawfile lspci_out "$tmp/lspci.out" --arg lspci_rc "$(cat "$tmp/lspci.rc")" --rawfile lspci_err "$tmp/lspci.err" \
  --rawfile lsusb_out "$tmp/lsusb.out" --arg lsusb_rc "$(cat "$tmp/lsusb.rc")" --rawfile lsusb_err "$tmp/lsusb.err" \
  --rawfile upower_out "$tmp/upower.out" --arg upower_rc "$(cat "$tmp/upower.rc")" --rawfile upower_err "$tmp/upower.err" \
  --rawfile edid_out "$tmp/edid.out" --arg edid_rc "$(cat "$tmp/edid.rc")" --rawfile edid_err "$tmp/edid.err" \
  --rawfile smart_out "$tmp/smart.out" --arg smart_rc "$(cat "$tmp/smart.rc")" --rawfile smart_err "$tmp/smart.err" \
  '
  def asjson($raw): (try ($raw|fromjson) catch null);
  def out_or_null($rc; $out):
    if ($rc|tonumber)==0 and ($out|length>0) then $out else null end;

  {
    schema: $schema,
    generated_at: $generated_at,
    scanner: { hostname: $hostname, user: $user },

    sources: {
      lshw:  (if ($lshw_rc|tonumber)==0 then asjson($lshw_raw) else null end),
      lsblk: (if ($lsblk_rc|tonumber)==0 then asjson($lsblk_raw) else null end),
      lspci:  out_or_null($lspci_rc;  $lspci_out),
      lsusb:  out_or_null($lsusb_rc;  $lsusb_out),
      upower: out_or_null($upower_rc; $upower_out),
      edid:   out_or_null($edid_rc;   $edid_out),
      smart:  out_or_null($smart_rc;  $smart_out)
    },

    meta: {
      status: {
        lshw:   { rc: ($lshw_rc|tonumber),   stderr: $lshw_err },
        lsblk:  { rc: ($lsblk_rc|tonumber),  stderr: $lsblk_err },
        lspci:  { rc: ($lspci_rc|tonumber),  stderr: $lspci_err },
        lsusb:  { rc: ($lsusb_rc|tonumber),  stderr: $lsusb_err },
        upower: { rc: ($upower_rc|tonumber), stderr: $upower_err },
        edid:   { rc: ($edid_rc|tonumber),   stderr: $edid_err },
        smart:  { rc: ($smart_rc|tonumber),  stderr: $smart_err }
      }
    }
  }' > "$OUT"

echo "Wrote bundle: $OUT"
BASH
