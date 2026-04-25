#!/bin/bash
# ==============================================================================
# USB Ethernet Watch
# ==============================================================================
# Called by udev when a USB ethernet interface (tethering, LTE dongle) appears
# or disappears. Triggers ethernet-autodetect.sh with the correct interface.
# ==============================================================================

exec >> /var/log/usb-ethernet-watch.log 2>&1
set -x

ACTION="${1:-$ACTION}"
IFACE="${2:-$INTERFACE}"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] - USB-ETH: $1" | systemd-cat -t usb-ethernet-watch
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] - USB-ETH: $1"
}

if [ -z "$IFACE" ]; then
    log "No interface specified"
    exit 1
fi

# Skip mesh/batman/bridge interfaces
case "$IFACE" in
    bat*|br*|wlan*|lo) exit 0 ;;
esac

# Confirm it's USB-backed
BUS=$(readlink /sys/class/net/$IFACE/device/subsystem 2>/dev/null | grep -o 'usb' || true)
if [ "$BUS" != "usb" ]; then
    log "$IFACE is not USB-backed, skipping"
    exit 0
fi

# Skip if native end0 is already the active gateway
if [ -f /var/run/upstream_iface ] && [ "$(cat /var/run/upstream_iface)" = "end0" ] && \
   [ -f /var/run/mesh-gateway.state ] && \
   ip route show dev end0 | grep -q '^default'; then
    log "end0 is already active gateway, ignoring $IFACE $ACTION"
    exit 0
fi

log "$ACTION on $IFACE"

case "$ACTION" in
    add|online)
        log "USB ethernet appeared: $IFACE — waiting for link..."
        sleep 3
        /usr/local/bin/ethernet-autodetect.sh --iface "$IFACE" --hotplug
        ;;
    remove|offline)
        log "USB ethernet removed: $IFACE — running cleanup"
        # Clear upstream_iface if it was this interface
        if [ -f /var/run/upstream_iface ] && [ "$(cat /var/run/upstream_iface)" = "$IFACE" ]; then
            rm -f /var/run/upstream_iface
        fi
        IFACE="$IFACE" /etc/networkd-dispatcher/off.d/50-gateway-disable 2>/dev/null || {
            rm -f /var/run/mesh-gateway.state /var/run/mesh-ntp.state /var/run/ethernet_detection_state
            ip addr flush dev "$IFACE" 2>/dev/null || true
            batctl gw_mode client 2>/dev/null || true
            nft flush chain ip nat postrouting 2>/dev/null || true
            systemctl restart gateway-route-manager.service 2>/dev/null || true
            systemctl restart dnsmasq.service 2>/dev/null || true
        }
        ;;
    *)
        log "Unknown action: $ACTION"
        exit 1
        ;;
esac

exit 0
