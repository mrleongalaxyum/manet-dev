#!/bin/bash
# Reboot all 4 MANET nodes
# Run with: bash reboot-all-nodes.sh

NODES=(192.168.1.50 192.168.1.51 192.168.1.53 192.168.1.198)
PASS="raspberry"
USER="radio"

for ip in "${NODES[@]}"; do
    echo "Rebooting $ip..."
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
        "$USER@$ip" "sudo reboot" 2>&1 && echo "  -> sent" || echo "  -> FAILED"
done

echo "Done. Nodes are rebooting."
