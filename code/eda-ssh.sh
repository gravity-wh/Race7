#!/bin/bash
# 用法: code/eda-ssh.sh '<远端命令>'
# 从 code/.eda_pw 读密码，经 SSH_ASKPASS 非交互登录（沙箱不允许 pty，故不用 sshpass）
set -u
PW_FILE="$(dirname "$0")/.eda_pw"
[ -r "$PW_FILE" ] || { echo "missing $PW_FILE" >&2; exit 2; }
AP=$(mktemp /tmp/ap.XXXXXX) || exit 2
cat > "$AP" <<'INNER'
#!/bin/sh
printf '%s\n' "$EDA_PW"
INNER
chmod 700 "$AP"
trap 'rm -f "$AP"' EXIT
export EDA_PW="$(cat "$PW_FILE")"
exec env SSH_ASKPASS="$AP" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
  setsid -w ssh -p 30025 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o LogLevel=ERROR -o ConnectTimeout=15 -o ServerAliveInterval=15 \
  -o PreferredAuthentications=password -o PubkeyAuthentication=no \
  -o NumberOfPasswordPrompts=1 eda260769@103.221.143.59 "$@"
