#!/bin/sh
# wan_mab_watchdog.sh - keepalive watchdog for an OpenWrt/ImmortalWrt edge router
# behind a campus network that hijacks unauthenticated traffic to a portal page.
#
# Idea: probe REAL site content. If the response body carries the portal marker
# (or an authentication page), the session is gone - physically bounce the WAN
# link, which re-triggers MAC-based auto authentication (MAB) on most campus
# access controllers. No credentials involved, no config is modified.
#
# Deploy:
#   ssh <router> 'cat > /usr/bin/wan_mab_watchdog.sh' < wan_mab_watchdog.sh
#   ssh <router> 'chmod +x /usr/bin/wan_mab_watchdog.sh; sh -n /usr/bin/wan_mab_watchdog.sh'
# Cron:
#   echo '*/3 * * * * /usr/bin/wan_mab_watchdog.sh' >> /etc/crontabs/root
#   /etc/init.d/cron restart
# Persist across sysupgrade: append this script, the log, the state file and
# /etc/crontabs/root to /etc/sysupgrade.conf.
#
# Usage: wan_mab_watchdog.sh [--status|--test|--force]
# Log:   $LOG    (default /etc/wan_mab.log)
# State: $STATE  (default /etc/wan_mab.state)
#
# Environment overrides (all optional):
#   PORTAL_MARK   marker string found in the hijack page (required to detect hijack)
#   PROBE_URLS    space separated probe targets, real content not captive-check URLs
#   WAN_IF        WAN interface name (default: wan)
#   FAIL_NEED     consecutive failures before bouncing (default 2)
#   COOLDOWN      base cooldown between bounces in seconds (default 900)
#   DOWN_SECONDS  how long the link stays down (default 25)
#   SETTLE        wait after the link is back before probing (default 25)

PORTAL_MARK="${PORTAL_MARK:-10.0.0.254}"
PROBE_URLS="${PROBE_URLS:-http://www.baidu.com http://www.163.com}"
WAN_IF="${WAN_IF:-wan}"
LOG="${LOG:-/etc/wan_mab.log}"
STATE="${STATE:-/etc/wan_mab.state}"
FAIL_NEED="${FAIL_NEED:-2}"
COOLDOWN="${COOLDOWN:-900}"
DOWN_SECONDS="${DOWN_SECONDS:-25}"
SETTLE="${SETTLE:-25}"
BACKOFF_STEP="${BACKOFF_STEP:-1800}"
BACKOFF_MAX="${BACKOFF_MAX:-7200}"
LOCK="/tmp/wan_mab.lock"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

fetch_head() {
    uclient-fetch -T 12 -O - "$1" 2>/dev/null | head -c 400
}

state_get() {
    if [ -f "$STATE" ]; then
        grep "^$1=" "$STATE" | tail -1 | cut -d= -f2-
    fi
}

state_set() {
    if [ -f "$STATE" ]; then
        grep -v "^$1=" "$STATE" > "$STATE.tmp" 2>/dev/null
        mv "$STATE.tmp" "$STATE" 2>/dev/null
    fi
    echo "$1=$2" >> "$STATE"
}

# return 0 = healthy, 1 = hijacked by portal, 2 = no connectivity
probe() {
    HIJACK=0
    for U in $PROBE_URLS; do
        B="$(fetch_head "$U")"
        if [ -z "$B" ]; then
            continue
        fi
        case "$B" in
            *"$PORTAL_MARK"*)
                HIJACK=1
                continue
                ;;
            *Authentication*)
                HIJACK=1
                continue
                ;;
            *)
                return 0
                ;;
        esac
    done
    if [ "$HIJACK" = "1" ]; then
        return 1
    fi
    return 2
}

probe_label() {
    case "$1" in
        0) echo "healthy" ;;
        1) echo "hijacked-by-portal" ;;
        *) echo "no-connectivity" ;;
    esac
}

bounce_wan() {
    log "action: physical WAN bounce, link down for ${DOWN_SECONDS}s"
    ip link set "$WAN_IF" down 2>>"$LOG"
    sleep "$DOWN_SECONDS"
    ip link set "$WAN_IF" up 2>>"$LOG"
    I=0
    while [ "$I" -lt 6 ]; do
        sleep 5
        if ip -4 addr show dev "$WAN_IF" 2>/dev/null | grep -q "inet "; then
            break
        fi
        I=$((I + 1))
    done
    if ! ip -4 addr show dev "$WAN_IF" 2>/dev/null | grep -q "inet "; then
        log "no WAN address after bounce, running ifup $WAN_IF"
        ifup "$WAN_IF" 2>>"$LOG"
        sleep 5
    fi
    A="$(ip -4 addr show dev "$WAN_IF" 2>/dev/null | grep -o 'inet [0-9.]*' | head -1)"
    log "WAN is up, address: $A"
    sleep "$SETTLE"
}

case "$1" in
    --status)
        echo "state:"
        cat "$STATE" 2>/dev/null
        echo "last log lines:"
        tail -12 "$LOG" 2>/dev/null
        probe
        R=$?
        echo "current probe: $(probe_label "$R")"
        exit 0
        ;;
    --test)
        probe
        R=$?
        log "manual probe only: $(probe_label "$R")"
        echo "probe: $(probe_label "$R")"
        exit "$R"
        ;;
    --force)
        log "manual force bounce requested"
        bounce_wan
        probe
        R=$?
        log "post-bounce probe: $(probe_label "$R")"
        exit "$R"
        ;;
esac

# ---------- main flow (run from cron) ----------
if [ -f "$LOCK" ]; then
    OLDPID="$(cat "$LOCK" 2>/dev/null)"
    if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
        exit 0
    fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

probe
R=$?

if [ "$R" = "0" ]; then
    FAILS="$(state_get fails)"
    FAILS=${FAILS:-0}
    if [ "$FAILS" -gt 0 ]; then
        log "link healthy again after ${FAILS} failed probes"
    fi
    state_set fails 0
    state_set last_ok "$(date '+%Y-%m-%d %H:%M:%S')"
    exit 0
fi

FAILS="$(state_get fails)"
FAILS=${FAILS:-0}
FAILS=$((FAILS + 1))
state_set fails "$FAILS"
log "probe result: $(probe_label "$R"), consecutive failures: $FAILS"

if [ "$FAILS" -lt "$FAIL_NEED" ]; then
    exit 0
fi

NOW="$(date +%s)"
LAST="$(state_get last_bounce_ts)"
LAST=${LAST:-0}
BOUNCES="$(state_get bounce_fails)"
BOUNCES=${BOUNCES:-0}
COOL=$((COOLDOWN + BOUNCES * BACKOFF_STEP))
if [ "$COOL" -gt "$BACKOFF_MAX" ]; then
    COOL=$BACKOFF_MAX
fi

if [ $((NOW - LAST)) -lt "$COOL" ]; then
    log "cooldown active, $((COOL - (NOW - LAST)))s left, consecutive bounce failures: $BOUNCES"
    exit 0
fi

bounce_wan
state_set last_bounce_ts "$(date +%s)"

probe
R=$?
if [ "$R" = "0" ]; then
    log "OK: WAN bounce restored the link"
    state_set fails 0
    state_set bounce_fails 0
    state_set last_ok "$(date '+%Y-%m-%d %H:%M:%S')"
else
    BOUNCES=$((BOUNCES + 1))
    state_set bounce_fails "$BOUNCES"
    state_set fails 0
    log "FAIL: still $(probe_label "$R") after bounce, bounce failures: $BOUNCES"
fi
