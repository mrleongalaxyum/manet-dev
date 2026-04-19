#!/usr/bin/env python3
"""
MANET Performance Dashboard
-----------------------------
Port 8081. Runs on all nodes. Accessible via wlan3 AP or LAN.

Endpoints:
  GET  /                        - Dashboard HTML
  GET  /api/topology            - Mesh topology (nodes, interfaces, hop counts)
  POST /api/interface/toggle    - Toggle wlan interface on node(s)
  POST /api/halow/channel       - Set HaLow channel/BW on all nodes
  POST /api/txpower             - Set TX power on node/interface
  POST /api/measure/start       - Start iperf3/ping session
  GET  /api/measure/status      - Current measurement status
  GET  /api/sessions            - List saved sessions
  GET  /api/sessions/<id>       - Get session JSON
  GET  /api/sessions/<id>/csv   - Get session CSV
  POST /api/upload/github       - Git push measurements/
  POST /api/upload/ventum       - SCP to Ventum
"""

import http.server
import socketserver
import json
import subprocess
import re
import os
import time
import threading
import csv
import io
import urllib.request
import ipaddress
from datetime import datetime, timezone
from urllib.parse import urlparse

PORT            = 8081
MESH_CONF_FILE  = '/etc/mesh.conf'
MESH_STATE_FILE = '/etc/mesh_ipv4_state'
REGISTRY_FILE   = '/var/run/mesh_node_registry'
SESSIONS_DIR    = '/var/log/manet-measurements'
CONTROL_PORT    = 80  # mesh-status.py port on each node

# EU S1G channels (centre frequencies in MHz)
HALOW_EU_CHANNELS = [863500, 864500, 865500, 866500, 867500, 868500]
HALOW_BW_OPTIONS  = ['1MHz', '2MHz', '4MHz']

# Active measurement state
_measure_lock   = threading.Lock()
_measure_status = {'running': False, 'label': '', 'progress': '', 'error': ''}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_kv_file(path):
    conf = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    conf[k.strip()] = v.strip().strip('"\'')
    except Exception:
        pass
    return conf

def norm_mac(mac):
    return mac.lower().replace('-', ':').strip()

def get_my_hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return 'unknown'

def get_my_ip():
    state = load_kv_file(MESH_STATE_FILE)
    return state.get('CURRENT_IPV4', '')

def has_internet():
    try:
        urllib.request.urlopen('https://github.com', timeout=3)
        return True
    except Exception:
        return False

def parse_registry():
    nodes = {}
    try:
        with open(REGISTRY_FILE) as f:
            content = f.read()
        pattern = re.compile(r"NODE_([A-Fa-f0-9]+)_([A-Z0-9_]+)='([^']*)'")
        for m in pattern.finditer(content):
            nid, field, value = m.groups()
            if nid not in nodes:
                nodes[nid] = {'id': nid}
            nodes[nid][field] = value
    except Exception:
        pass
    return nodes

def get_bat0_active_ifaces():
    try:
        r = subprocess.run(['batctl', 'if'], capture_output=True, text=True, timeout=5)
        return [l.split(':')[0].strip() for l in r.stdout.splitlines() if 'active' in l]
    except Exception:
        return []

def get_hop_count(dst_ip):
    """Estimate hop count to dst_ip via traceroute (max 5 hops, fast)."""
    try:
        r = subprocess.run(
            ['traceroute', '-n', '-m', '5', '-w', '1', dst_ip],
            capture_output=True, text=True, timeout=10
        )
        hops = [l for l in r.stdout.splitlines()
                if re.match(r'\s*\d+\s+[\d.]', l) and '* * *' not in l]
        return len(hops)
    except Exception:
        return None

def call_node_api(node_ip, path, method='GET', data=None):
    """Call mesh-status.py control API on a remote node."""
    try:
        url = f'http://{node_ip}:{CONTROL_PORT}{path}'
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={'Content-Type': 'application/json', 'User-Agent': 'perf-dashboard/1'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def get_iw_info(iface):
    """Get current channel/freq/txpower for an interface."""
    info = {}
    try:
        r = subprocess.run(['iw', 'dev', iface, 'info'],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r'channel (\d+).*?(\d+) MHz', r.stdout)
        if m:
            info['channel'] = m.group(1)
            info['freq_mhz'] = m.group(2)
        m = re.search(r'txpower ([\d.]+) dBm', r.stdout)
        if m:
            info['txpower_dbm'] = m.group(1)
    except Exception:
        pass
    return info

# ─────────────────────────────────────────────────────────────────────────────
# Topology
# ─────────────────────────────────────────────────────────────────────────────
def build_topology():
    nodes_raw = parse_registry()
    my_host   = get_my_hostname()
    my_ip     = get_my_ip()
    conf      = load_kv_file(MESH_CONF_FILE)

    # Get local interface state
    active_ifaces = get_bat0_active_ifaces()
    iw_wlan0 = get_iw_info('wlan0')
    iw_wlan1 = get_iw_info('wlan1')
    iw_wlan2 = get_iw_info('wlan2')

    nodes = []
    for nid, nd in nodes_raw.items():
        hostname = nd.get('HOSTNAME', 'unknown')
        ip       = nd.get('IPV4_ADDRESS', '')
        is_me    = (hostname == my_host)

        node_info = {
            'id':       nid,
            'hostname': hostname,
            'ip':       ip,
            'is_me':    is_me,
            'is_gateway': nd.get('IS_GATEWAY', 'false').lower() == 'true',
            'battery':  nd.get('BATTERY_PERCENTAGE', ''),
            'uptime':   nd.get('UPTIME_SECONDS', ''),
        }

        if is_me:
            node_info['interfaces'] = {
                'wlan0': {'active': 'wlan0' in active_ifaces, **iw_wlan0},
                'wlan1': {'active': 'wlan1' in active_ifaces, **iw_wlan1},
                'wlan2': {'active': 'wlan2' in active_ifaces, **iw_wlan2},
            }
        else:
            # Fetch from remote node's /api/local via peer proxy
            try:
                local = call_node_api(ip, '/api/local')
                ifaces_raw = local.get('interfaces', [])
                node_info['interfaces'] = {
                    i['name']: {
                        'active': i.get('health') == 'ok' and i.get('role') == 'mesh',
                        'channel': '',
                        'freq_mhz': '',
                    }
                    for i in ifaces_raw if i.get('name') in ('wlan0', 'wlan1', 'wlan2')
                }
            except Exception:
                node_info['interfaces'] = {}

        nodes.append(node_info)

    # Sort: self first
    nodes.sort(key=lambda n: (not n['is_me'], n['hostname']))

    # Build hop count matrix
    hop_matrix = {}
    for src in nodes:
        for dst in nodes:
            if src['id'] == dst['id']:
                continue
            key = f"{src['id']}-{dst['id']}"
            if src['is_me'] and dst.get('ip'):
                hop_matrix[key] = get_hop_count(dst['ip'])
            else:
                hop_matrix[key] = None

    return {
        'nodes':      nodes,
        'hop_matrix': hop_matrix,
        'my_hostname': my_host,
        'my_ip':      my_ip,
        'internet':   has_internet(),
        'timestamp':  int(time.time()),
    }

# ─────────────────────────────────────────────────────────────────────────────
# Measurements
# ─────────────────────────────────────────────────────────────────────────────
def ensure_sessions_dir():
    os.makedirs(SESSIONS_DIR, exist_ok=True)

def list_sessions():
    ensure_sessions_dir()
    sessions = []
    for name in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        d = os.path.join(SESSIONS_DIR, name)
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.endswith('.json')]
            sessions.append({'label': name, 'tests': len(files)})
    return sessions

def get_session_results(label):
    d = os.path.join(SESSIONS_DIR, label)
    results = []
    if not os.path.isdir(d):
        return results
    for fname in sorted(os.listdir(d)):
        if fname.endswith('.json'):
            try:
                with open(os.path.join(d, fname)) as f:
                    results.append(json.load(f))
            except Exception:
                pass
    return results

def session_to_csv(label):
    results = get_session_results(label)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'timestamp', 'session_label', 'test_type',
        'src_node', 'dst_node', 'hop_count',
        'active_interfaces', 'halow_channel', 'halow_bw',
        'tcp_mbps', 'udp_mbps', 'jitter_ms', 'loss_pct',
        'rtt_avg_ms', 'rtt_min_ms', 'rtt_max_ms',
    ])
    for r in results:
        iperf = r.get('iperf3_result', {})
        ping  = r.get('ping_result', {})
        # Extract iperf3 metrics
        tcp_mbps = udp_mbps = jitter = loss = None
        try:
            end = iperf.get('end', {})
            if 'sum_received' in end:
                tcp_mbps = round(end['sum_received']['bits_per_second'] / 1e6, 2)
            if 'sum' in end:
                s = end['sum']
                udp_mbps = round(s.get('bits_per_second', 0) / 1e6, 2)
                jitter   = round(s.get('jitter_ms', 0), 3)
                loss     = round(s.get('lost_percent', 0), 2)
        except Exception:
            pass
        writer.writerow([
            r.get('timestamp', ''),
            r.get('session_label', ''),
            r.get('test_type', ''),
            r.get('source_node', ''),
            r.get('destination_node', ''),
            r.get('hop_count', ''),
            ','.join(r.get('active_interfaces', [])),
            r.get('halow_channel', ''),
            r.get('halow_bw', ''),
            tcp_mbps or '',
            udp_mbps or '',
            jitter or '',
            loss or (ping.get('loss_pct', '') if ping else ''),
            ping.get('rtt_avg', '') if ping else '',
            ping.get('rtt_min', '') if ping else '',
            ping.get('rtt_max', '') if ping else '',
        ])
    return output.getvalue()

def snapshot_topology():
    """Lightweight topology snapshot for embedding in test results."""
    active = get_bat0_active_ifaces()
    iw2    = get_iw_info('wlan2')
    iw0    = get_iw_info('wlan0')
    return {
        'active_interfaces': active,
        'halow_channel':  iw2.get('freq_mhz', ''),
        'halow_bw':       '',
        'ch_2g':          iw0.get('channel', ''),
    }

def run_measurement_session(label, pairs, tests, duration, udp_bitrate):
    """Run all test combinations. Blocking — call in thread."""
    global _measure_status
    ensure_sessions_dir()
    session_dir = os.path.join(SESSIONS_DIR, label)
    os.makedirs(session_dir, exist_ok=True)
    topo = snapshot_topology()

    total = len(pairs) * len(tests)
    done  = 0

    for pair in pairs:
        src_ip   = pair['src_ip']
        dst_ip   = pair['dst_ip']
        src_name = pair['src_name']
        dst_name = pair['dst_name']
        hop_count = pair.get('hop_count')

        for test_type in tests:
            with _measure_lock:
                _measure_status['progress'] = f'{src_name}→{dst_name} {test_type} ({done+1}/{total})'

            ts    = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            fname = f'{ts}_{src_name}_{dst_name}_{test_type}.json'
            result_record = {
                'session_label':    label,
                'timestamp':        datetime.now(timezone.utc).isoformat(),
                'test_type':        test_type,
                'source_node':      src_name,
                'destination_node': dst_name,
                'hop_count':        hop_count,
                'active_interfaces': topo['active_interfaces'],
                'halow_channel':    topo['halow_channel'],
                'halow_bw':         topo['halow_bw'],
                'ch_2g':            topo['ch_2g'],
                'gps_source':       None,
                'gps_destination':  None,
            }

            if test_type == 'icmp_ping':
                # Run ping locally toward dst
                resp = call_node_api(src_ip, '/api/ping/run', 'POST', {
                    'target': dst_ip, 'count': 100, 'interval': 0.2
                })
                result_record['ping_result'] = resp.get('result')
                result_record['ok'] = resp.get('ok', False)
            else:
                # Start iperf3 server on dst, run client on src
                call_node_api(dst_ip, '/api/iperf/server/start', 'POST', {})
                time.sleep(1)

                reverse = test_type == 'reverse'
                parallel = 4 if test_type == 'tcp_4stream' else 1
                resp = call_node_api(src_ip, '/api/iperf/client/run', 'POST', {
                    'server_ip':  dst_ip,
                    'test_type':  test_type,
                    'duration':   duration,
                    'bitrate':    udp_bitrate,
                    'parallel':   parallel,
                    'reverse':    reverse,
                })
                result_record['iperf3_result'] = resp.get('result')
                result_record['ok'] = resp.get('ok', False)
                call_node_api(dst_ip, '/api/iperf/server/stop', 'POST', {})

            # Save result
            with open(os.path.join(session_dir, fname), 'w') as f:
                json.dump(result_record, f, indent=2)

            done += 1
            time.sleep(2)  # brief pause between tests

    with _measure_lock:
        _measure_status['running']  = False
        _measure_status['progress'] = f'Done — {done} tests saved'

# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
:root {
  --bg:      #06080a;
  --surface: #0c1117;
  --card:    #0f1923;
  --border:  #1a2e42;
  --border2: #0e2030;
  --accent:  #00e5ff;
  --accent2: #0091b8;
  --green:   #00ff88;
  --orange:  #ff8800;
  --red:     #ff2244;
  --purple:  #7c6cff;
  --text:    #c8d8e8;
  --muted:   #4a6478;
  --font:    'Share Tech Mono', 'Courier New', monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:13px;min-height:100vh}

/* scanline overlay */
body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.08) 2px,rgba(0,0,0,.08) 4px);pointer-events:none;z-index:9999}

/* header */
#hdr{background:var(--surface);border-bottom:2px solid var(--accent);padding:0 20px;height:48px;display:flex;align-items:center;gap:20px;position:sticky;top:0;z-index:100}
#hdr-logo{color:var(--accent);font-size:18px;letter-spacing:4px;font-weight:700;text-shadow:0 0 20px var(--accent)}
#hdr-logo span{color:var(--green);text-shadow:0 0 20px var(--green)}
#hdr-node{font-size:11px;color:var(--muted);border-left:1px solid var(--border);padding-left:16px}
#hdr-node strong{color:var(--text)}
#hdr-right{margin-left:auto;display:flex;align-items:center;gap:16px;font-size:11px}
#hdr-inet{padding:3px 10px;border-radius:2px;letter-spacing:1px;font-size:10px}
#hdr-inet.ok{color:var(--green);border:1px solid #00ff8840;background:#00ff8808;text-shadow:0 0 8px var(--green)}
#hdr-inet.no{color:var(--orange);border:1px solid #ff880040;background:#ff880008}
#hdr-clock{color:var(--muted);font-size:11px}

/* nav */
#nav{background:var(--surface);border-bottom:1px solid var(--border2);display:flex;padding:0 20px}
.tab{padding:12px 20px;cursor:pointer;font-size:11px;letter-spacing:2px;color:var(--muted);border-bottom:2px solid transparent;text-transform:uppercase;transition:all .15s;position:relative}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-color:var(--accent);text-shadow:0 0 10px var(--accent)}
.tab.active::after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:1px;background:var(--accent);box-shadow:0 0 8px var(--accent)}

/* layout */
#content{padding:20px;max-width:1100px}

/* card */
.card{background:var(--card);border:1px solid var(--border);margin-bottom:16px;position:relative;overflow:hidden}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:.4}
.card-title{padding:10px 16px;font-size:10px;letter-spacing:2px;color:var(--accent);text-transform:uppercase;border-bottom:1px solid var(--border2);display:flex;align-items:center;gap:8px}
.card-title::before{content:'//';color:var(--muted)}

/* rows */
.row{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border2);flex-wrap:wrap}
.row:last-child{border-bottom:none}
.row-label{flex:0 0 150px;font-size:11px;color:var(--muted);letter-spacing:.5px;text-transform:uppercase}

/* inputs */
input[type=text],input[type=number],select{
  background:#060c12;border:1px solid var(--border);color:var(--text);
  padding:6px 10px;font-family:var(--font);font-size:12px;
  outline:none;transition:border .15s;min-width:150px;
}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 8px #00e5ff20}
select option{background:#0c1117}
input[type=checkbox]{width:15px;height:15px;accent-color:var(--accent)}

/* buttons */
.btn{padding:7px 16px;background:transparent;color:var(--accent);border:1px solid var(--accent);font-family:var(--font);font-size:11px;cursor:pointer;letter-spacing:1.5px;text-transform:uppercase;transition:all .15s;position:relative;overflow:hidden}
.btn::before{content:'';position:absolute;inset:0;background:var(--accent);opacity:0;transition:opacity .15s}
.btn:hover::before{opacity:.1}
.btn:hover{box-shadow:0 0 12px #00e5ff40;text-shadow:0 0 8px var(--accent)}
.btn:disabled{opacity:.3;cursor:not-allowed;box-shadow:none}
.btn-red{color:var(--red);border-color:var(--red)}
.btn-red:hover::before{background:var(--red)}
.btn-red:hover{box-shadow:0 0 12px #ff224440}
.btn-green{color:var(--green);border-color:var(--green)}
.btn-green:hover::before{background:var(--green)}
.btn-run{padding:12px 32px;font-size:13px;color:var(--green);border-color:var(--green);letter-spacing:3px}
.btn-run:hover{box-shadow:0 0 20px #00ff8840}

/* badges */
.badge{padding:2px 8px;font-size:10px;letter-spacing:.5px;border:1px solid}
.b-on {color:var(--green); border-color:#00ff8840;background:#00ff8810}
.b-off{color:var(--muted); border-color:#1a2e4260;background:transparent}
.b-gw {color:var(--orange);border-color:#ff880040;background:#ff880010}
.b-me {color:var(--purple);border-color:#7c6cff40;background:#7c6cff10}
.b-hop{color:var(--accent); border-color:#00e5ff30;background:#00e5ff08;font-size:9px}

/* table */
table{width:100%;border-collapse:collapse}
thead tr{border-bottom:1px solid var(--border)}
th{padding:8px 12px;font-size:9px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;text-align:left}
td{padding:10px 12px;border-bottom:1px solid var(--border2);font-size:12px;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#0f1923}

/* node grid */
.node-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;padding:16px}
.node-card{background:#060c12;border:1px solid var(--border2);padding:14px;position:relative;transition:border .15s}
.node-card:hover{border-color:var(--border)}
.node-card.is-me{border-color:#7c6cff50}
.node-card.is-gw{border-color:#ff880050}
.node-name{font-size:14px;font-weight:700;margin-bottom:4px;color:var(--text)}
.node-ip{font-size:10px;color:var(--muted);margin-bottom:8px}
.node-ifaces{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px}
.iface-chip{font-size:9px;padding:2px 6px;border:1px solid}
.iface-on {color:var(--green);border-color:#00ff8840;background:#00ff8808}
.iface-off{color:var(--muted);border-color:#1a2e4260}
.node-battery{font-size:10px;color:var(--muted)}
.node-tags{position:absolute;top:10px;right:10px;display:flex;gap:4px}

/* interface toggle cards */
.iface-block{padding:12px 16px;border-bottom:1px solid var(--border2)}
.iface-block:last-child{border-bottom:none}
.iface-header{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.iface-name{font-size:13px;font-weight:700;min-width:60px}
.iface-band{font-size:10px;color:var(--muted);letter-spacing:.5px}
.iface-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.txpwr-row{display:flex;align-items:center;gap:8px;margin-top:4px;padding-left:72px;font-size:11px;color:var(--muted)}

/* global actions bar */
.global-bar{display:flex;gap:8px;flex-wrap:wrap;padding:12px 16px}

/* pairs */
.pairs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:6px;padding:12px 16px}
.pair-item{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#060c12;border:1px solid var(--border2);cursor:pointer;transition:border .15s}
.pair-item:hover{border-color:var(--border)}
.pair-item input{flex-shrink:0}
.pair-label{font-size:12px;flex:1}
.pair-arrow{color:var(--accent);margin:0 4px}

/* tests */
.tests-wrap{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px}
.test-chip{display:flex;align-items:center;gap:6px;padding:6px 12px;background:#060c12;border:1px solid var(--border2);cursor:pointer;font-size:11px;transition:all .15s;letter-spacing:.5px}
.test-chip:has(input:checked){border-color:var(--accent);color:var(--accent);background:#00e5ff08}
.test-chip:hover{border-color:var(--border)}

/* progress */
.progress-wrap{padding:12px 16px}
.progress-label{font-size:11px;color:var(--muted);margin-bottom:6px;letter-spacing:.5px}
.progress-bar-bg{height:3px;background:#1a2e42;position:relative}
.progress-bar-fill{height:3px;background:var(--accent);box-shadow:0 0 6px var(--accent);transition:width .3s;width:0}
.progress-text{font-size:12px;color:var(--accent);margin-top:6px;min-height:18px}
.progress-text.done{color:var(--green)}
.progress-text.err{color:var(--red)}

/* msg */
#msg{padding:10px 16px;font-size:12px;display:none;margin-bottom:16px;border-left:3px solid;letter-spacing:.3px}
#msg.ok  {border-color:var(--green);color:var(--green);background:#00ff8808;display:block}
#msg.err {border-color:var(--red);  color:var(--red);  background:#ff224408;display:block}
#msg.info{border-color:var(--accent);color:var(--accent);background:#00e5ff08;display:block}

/* session list */
.session-row{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border2)}
.session-row:last-child{border-bottom:none}
.session-label{flex:1;font-size:13px}
.session-count{font-size:11px;color:var(--muted)}
.session-actions{display:flex;gap:6px}

/* upload */
.upload-card{padding:16px;display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--border2)}
.upload-card:last-child{border-bottom:none}
.upload-info{flex:1}
.upload-title{font-size:13px;margin-bottom:2px}
.upload-sub{font-size:10px;color:var(--muted);letter-spacing:.3px}
"""

JS = """
let _topo = null;
let _tab  = 'topology';

async function fetchTopo() {
  try {
    const r = await fetch('/api/topology');
    _topo = await r.json();
    renderTopology();
    updatePairs();
  } catch(e) { showMsg('Topology fetch failed: ' + e, 'err'); }
}

function showMsg(txt, cls) {
  const el = document.getElementById('msg');
  el.textContent = txt; el.className = cls;
  setTimeout(() => { el.style.display = 'none'; }, 5000);
}

function showTab(name) {
  _tab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.style.display = p.id === 'tab-' + name ? '' : 'none');
  if (name === 'sessions') loadSessions();
}

// ── Clock ──
function tickClock() {
  const el = document.getElementById('hdr-clock');
  if (el) el.textContent = new Date().toISOString().replace('T',' ').substring(0,19) + ' UTC';
}
setInterval(tickClock, 1000); tickClock();

// ── Topology tab ──
function renderTopology() {
  if (!_topo) return;
  const grid = document.getElementById('node-grid');
  grid.innerHTML = '';
  for (const node of _topo.nodes) {
    const ifaces = node.interfaces || {};
    const chips = ['wlan0','wlan1','wlan2'].map(i => {
      const info = ifaces[i] || {};
      const on = info.active !== false;
      const band = i === 'wlan0' ? '2.4G' : i === 'wlan1' ? '5G' : 'HaLow';
      const ch = info.channel ? ` ch${info.channel}` : (info.freq_mhz ? ` ${Math.round(info.freq_mhz)}MHz` : '');
      return `<span class="iface-chip ${on ? 'iface-on' : 'iface-off'}">${band}${on ? ch : ' OFF'}</span>`;
    }).join('');
    const bat = node.battery ? `<div class="node-battery">BAT ${node.battery}%</div>` : '';
    const tags = [
      node.is_me ? '<span class="badge b-me" style="font-size:9px">ME</span>' : '',
      node.is_gateway ? '<span class="badge b-gw" style="font-size:9px">GW</span>' : '',
    ].filter(Boolean).join('');
    const cls = [node.is_me ? 'is-me' : '', node.is_gateway ? 'is-gw' : ''].join(' ');
    grid.innerHTML += `<div class="node-card ${cls}">
      <div class="node-tags">${tags}</div>
      <div class="node-name">${node.hostname}</div>
      <div class="node-ip">${node.ip}</div>
      <div class="node-ifaces">${chips}</div>
      ${bat}
    </div>`;
  }

  // Hop matrix
  const hm = document.getElementById('hop-matrix');
  if (_topo.hop_matrix && _topo.nodes.length > 1) {
    const nodes = _topo.nodes;
    let html = '<table><thead><tr><th></th>';
    for (const dst of nodes) html += `<th>${dst.hostname}</th>`;
    html += '</tr></thead><tbody>';
    for (const src of nodes) {
      html += `<tr><td style="color:var(--text);font-weight:bold">${src.hostname}</td>`;
      for (const dst of nodes) {
        if (src.id === dst.id) { html += '<td style="color:var(--border)">—</td>'; continue; }
        const h = _topo.hop_matrix[`${src.id}-${dst.id}`];
        const v = h != null ? h : '?';
        html += `<td><span class="badge b-hop">${v} hop${v !== 1 ? 's' : ''}</span></td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    hm.innerHTML = html;
  } else {
    hm.innerHTML = '<span style="color:var(--muted);font-size:11px">Hop data unavailable</span>';
  }

  // Internet + upload buttons
  const inet = document.getElementById('hdr-inet');
  if (_topo.internet) { inet.textContent = '● INET OK'; inet.className = 'ok'; }
  else { inet.textContent = '○ NO INET'; inet.className = 'no'; }
  document.getElementById('upload-github').disabled = !_topo.internet;
  document.getElementById('upload-ventum').disabled = !_topo.internet;
}

// ── Interface control tab ──
function buildIfaceControl() {
  if (!_topo) return;
  const wrap = document.getElementById('iface-cards');
  wrap.innerHTML = '';
  for (const node of _topo.nodes) {
    const ifaces = node.interfaces || {};
    const card = document.createElement('div');
    card.className = 'card';
    const BANDS = {wlan0: '2.4 GHz', wlan1: '5 GHz', wlan2: 'HaLow 900 MHz'};
    let html = `<div class="card-title">${node.hostname} &nbsp;<span style="color:var(--muted);font-size:10px">${node.ip}${node.is_me ? ' &bull; THIS NODE' : ''}</span></div>`;
    for (const iface of ['wlan0','wlan1','wlan2']) {
      const info = ifaces[iface] || {};
      const on = info.active !== false;
      html += `<div class="iface-block">
        <div class="iface-header">
          <span class="iface-name">${iface}</span>
          <span class="iface-band">${BANDS[iface]}</span>
          <span class="badge ${on ? 'b-on' : 'b-off'}" id="ibadge-${node.id}-${iface}">${on ? 'ACTIVE' : 'DOWN'}</span>
          <div class="iface-controls">
            ${on
              ? `<button class="btn btn-red" onclick="toggleIface('${node.ip}','${node.id}','${iface}','down')">DISABLE</button>`
              : `<button class="btn btn-green" onclick="toggleIface('${node.ip}','${node.id}','${iface}','up')">ENABLE</button>`
            }
          </div>
        </div>
        <div class="txpwr-row">
          TX POWER
          <input type="number" id="txpwr-${node.id}-${iface}" value="${info.txpower_dbm || 20}" min="0" max="30" style="width:65px">
          dBm
          <button class="btn" style="padding:4px 10px;font-size:10px" onclick="setTxPower('${node.ip}','${node.id}','${iface}')">SET</button>
        </div>
      </div>`;
    }
    card.innerHTML = html;
    wrap.appendChild(card);
  }
}

async function toggleIface(nodeIp, nodeId, iface, state) {
  const r = await fetch('/api/interface/toggle', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({node_ip: nodeIp, iface, state})
  });
  const d = await r.json();
  if (d.ok) { showMsg(`${iface} ${state} on ${nodeIp}`, 'ok'); await fetchTopo(); buildIfaceControl(); }
  else showMsg('Error: ' + d.error, 'err');
}

async function setTxPower(nodeIp, nodeId, iface) {
  const dbm = document.getElementById(`txpwr-${nodeId}-${iface}`).value;
  const r = await fetch('/api/txpower', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({node_ip: nodeIp, iface, dbm: parseFloat(dbm)})
  });
  const d = await r.json();
  if (d.ok) showMsg(`TX power set to ${dbm}dBm on ${iface}@${nodeIp}`, 'ok');
  else showMsg('Error: ' + d.error, 'err');
}

async function toggleAll(iface, state) {
  const r = await fetch('/api/interface/toggle', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({node_ip: 'all', iface, state})
  });
  const d = await r.json();
  if (d.ok) { showMsg(`${iface} ${state} on all nodes`, 'ok'); await fetchTopo(); buildIfaceControl(); }
  else showMsg('Error: ' + d.error, 'err');
}

// ── HaLow config tab (HTML is static in template) ──
function buildHalowConfig() {}

async function applyHalow() {
  const ch = document.getElementById('halow-ch').value;
  const bw = document.getElementById('halow-bw').value;
  const r = await fetch('/api/halow/channel', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({channel: parseInt(ch), bw})
  });
  const d = await r.json();
  if (d.ok) showMsg('HaLow channel applied to all nodes', 'ok');
  else showMsg('Error: ' + d.error, 'err');
}

async function apply2G() {
  const ch = document.getElementById('ch-2g').value;
  const r = await fetch('/api/halow/channel', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({interface: 'wlan0', channel: parseInt(ch)})
  });
  const d = await r.json();
  if (d.ok) showMsg('2.4G channel applied to all nodes', 'ok');
  else showMsg('Error: ' + d.error, 'err');
}

// ── Measurements tab ──
function updatePairs() {
  if (!_topo) return;
  const wrap = document.getElementById('pairs-grid');
  wrap.innerHTML = '';
  const nodes = _topo.nodes;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = 0; j < nodes.length; j++) {
      if (i === j) continue;
      const src = nodes[i], dst = nodes[j];
      const key = `${src.id}-${dst.id}`;
      const hops = (_topo.hop_matrix || {})[key];
      const hopBadge = hops != null ? `<span class="badge badge-hop">${hops} hop${hops>1?'s':''}</span>` : '';
      wrap.innerHTML += `
        <div class="pair-row">
          <input type="checkbox" id="pair-${key}" value="${key}" data-src="${src.ip}" data-dst="${dst.ip}" data-src-name="${src.hostname}" data-dst-name="${dst.hostname}" data-hops="${hops||''}">
          <label for="pair-${key}" style="flex:none;font-size:12px">${src.hostname} → ${dst.hostname}</label>
          ${hopBadge}
        </div>`;
    }
  }
}

async function startMeasurement() {
  const label = document.getElementById('session-label').value.trim();
  if (!label) { showMsg('Enter a session label', 'err'); return; }

  const pairs = [];
  document.querySelectorAll('#pairs-grid input:checked').forEach(el => {
    pairs.push({
      src_ip: el.dataset.src, dst_ip: el.dataset.dst,
      src_name: el.dataset.srcName || el.dataset.src,
      dst_name: el.dataset.dstName || el.dataset.dst,
      hop_count: el.dataset.hops ? parseInt(el.dataset.hops) : null,
    });
  });
  if (!pairs.length) { showMsg('Select at least one test pair', 'err'); return; }

  const tests = [];
  document.querySelectorAll('#tests-grid input:checked').forEach(el => tests.push(el.value));
  if (!tests.length) { showMsg('Select at least one test type', 'err'); return; }

  const duration   = parseInt(document.getElementById('duration').value) || 30;
  const udpBitrate = document.getElementById('udp-bitrate').value || '4M';

  document.getElementById('btn-run').disabled = true;
  showMsg('Starting measurement session...', 'info');

  const r = await fetch('/api/measure/start', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({label, pairs, tests, duration, udp_bitrate: udpBitrate})
  });
  const d = await r.json();
  if (d.ok) {
    showMsg('Running...', 'info');
    pollStatus();
  } else {
    showMsg('Error: ' + d.error, 'err');
    document.getElementById('btn-run').disabled = false;
  }
}

async function pollStatus() {
  const r = await fetch('/api/measure/status');
  const d = await r.json();
  const card = document.getElementById('progress-card');
  const txt  = document.getElementById('progress-text');
  const fill = document.getElementById('progress-fill');
  card.style.display = '';
  txt.textContent = d.progress || '';
  txt.className = 'progress-text' + (d.running ? '' : d.error ? ' err' : ' done');
  // Pulse bar while running
  if (d.running) {
    fill.style.width = '60%';
    setTimeout(pollStatus, 2000);
  } else {
    fill.style.width = d.error ? '100%' : '100%';
    fill.style.background = d.error ? 'var(--red)' : 'var(--green)';
    document.getElementById('btn-run').disabled = false;
    if (d.error) showMsg('Error: ' + d.error, 'err');
    else showMsg('Measurement complete — results saved.', 'ok');
    loadSessions();
  }
}

// ── Sessions tab ──
async function loadSessions() {
  const r = await fetch('/api/sessions');
  const d = await r.json();
  const list = document.getElementById('sessions-list');
  if (!d.length) {
    list.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:11px">No sessions recorded yet.</div>';
    return;
  }
  list.innerHTML = d.map(s => `
    <div class="session-row">
      <div class="session-label">${s.label}</div>
      <div class="session-count">${s.tests} test${s.tests !== 1 ? 's' : ''}</div>
      <div class="session-actions">
        <a href="/api/sessions/${encodeURIComponent(s.label)}/csv" download="${s.label}.csv"
           class="btn" style="text-decoration:none;font-size:10px">CSV</a>
        <a href="/api/sessions/${encodeURIComponent(s.label)}" target="_blank"
           class="btn" style="text-decoration:none;font-size:10px">JSON</a>
      </div>
    </div>`).join('');
}

async function uploadGithub() {
  document.getElementById('upload-github').disabled = true;
  const r = await fetch('/api/upload/github', {method:'POST'});
  const d = await r.json();
  document.getElementById('upload-github').disabled = !_topo?.internet;
  if (d.ok) showMsg('Uploaded to GitHub', 'ok');
  else showMsg('GitHub upload failed: ' + d.error, 'err');
}

async function uploadVentum() {
  document.getElementById('upload-ventum').disabled = true;
  const r = await fetch('/api/upload/ventum', {method:'POST'});
  const d = await r.json();
  document.getElementById('upload-ventum').disabled = !_topo?.internet;
  if (d.ok) showMsg('Uploaded to Ventum', 'ok');
  else showMsg('Ventum upload failed: ' + d.error, 'err');
}

window.onload = async () => {
  showTab('topology');
  await fetchTopo();
  buildIfaceControl();
  buildHalowConfig();
};
"""

def render_dashboard():
    hostname = get_my_hostname()
    ip       = get_my_ip()
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MANET // PERF</title>
<style>{CSS}</style>
</head><body>

<div id="hdr">
  <div id="hdr-logo">MANET//<span>PERF</span></div>
  <div id="hdr-node"><strong>{hostname}</strong> &nbsp;{ip}</div>
  <div id="hdr-right">
    <span id="hdr-inet" class="no">○ NO INET</span>
    <span id="hdr-clock"></span>
  </div>
</div>

<div id="nav">
  <div class="tab active" data-tab="topology"   onclick="showTab('topology')">TOPOLOGY</div>
  <div class="tab"        data-tab="interfaces" onclick="showTab('interfaces')">INTERFACES</div>
  <div class="tab"        data-tab="radio"      onclick="showTab('radio')">RADIO CONFIG</div>
  <div class="tab"        data-tab="measure"    onclick="showTab('measure')">MEASURE</div>
  <div class="tab"        data-tab="sessions"   onclick="showTab('sessions')">SESSIONS</div>
  <div class="tab"        data-tab="upload"     onclick="showTab('upload')">UPLOAD</div>
</div>

<div id="content">
  <div id="msg"></div>

  <!-- ── TOPOLOGY ── -->
  <div id="tab-topology" class="tab-pane">
    <div class="card">
      <div class="card-title">Mesh Nodes</div>
      <div class="node-grid" id="node-grid">
        <div style="padding:20px;color:var(--muted);font-size:11px">Loading topology...</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Hop Count Matrix</div>
      <div id="hop-matrix" style="padding:12px 16px;font-size:11px;color:var(--muted)">Loading...</div>
    </div>
  </div>

  <!-- ── INTERFACES ── -->
  <div id="tab-interfaces" class="tab-pane" style="display:none">
    <div class="card">
      <div class="card-title">Global Actions</div>
      <div class="global-bar" id="global-bar">
        <button class="btn btn-green" onclick="toggleAll('wlan0','up')">↑ 2.4G ALL</button>
        <button class="btn btn-red"   onclick="toggleAll('wlan0','down')">↓ 2.4G ALL</button>
        <button class="btn btn-green" onclick="toggleAll('wlan1','up')">↑ 5G ALL</button>
        <button class="btn btn-red"   onclick="toggleAll('wlan1','down')">↓ 5G ALL</button>
        <button class="btn btn-green" onclick="toggleAll('wlan2','up')">↑ HALOW ALL</button>
        <button class="btn btn-red"   onclick="toggleAll('wlan2','down')">↓ HALOW ALL</button>
      </div>
    </div>
    <div id="iface-cards"></div>
  </div>

  <!-- ── RADIO CONFIG ── -->
  <div id="tab-radio" class="tab-pane" style="display:none">
    <div class="card">
      <div class="card-title">HaLow 900 MHz</div>
      <div class="row">
        <span class="row-label">Channel</span>
        <select id="halow-ch">
          <option value="863500">863.5 MHz</option>
          <option value="864500">864.5 MHz</option>
          <option value="865500">865.5 MHz</option>
          <option value="866500" selected>866.5 MHz</option>
          <option value="867500">867.5 MHz</option>
          <option value="868500">868.5 MHz</option>
        </select>
      </div>
      <div class="row">
        <span class="row-label">Bandwidth</span>
        <select id="halow-bw">
          <option value="1MHz">1 MHz</option>
          <option value="2MHz" selected>2 MHz</option>
          <option value="4MHz">4 MHz</option>
        </select>
      </div>
      <div class="row">
        <span class="row-label"></span>
        <button class="btn btn-green" onclick="applyHalow()">APPLY TO ALL NODES</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title">2.4 GHz</div>
      <div class="row">
        <span class="row-label">Channel</span>
        <select id="ch-2g">
          ${''.join(f'<option value="{c}"{" selected" if c==6 else ""}>{c}</option>' for c in range(1,14))}
        </select>
      </div>
      <div class="row">
        <span class="row-label"></span>
        <button class="btn btn-green" onclick="apply2G()">APPLY TO ALL NODES</button>
      </div>
    </div>
  </div>

  <!-- ── MEASURE ── -->
  <div id="tab-measure" class="tab-pane" style="display:none">
    <div class="card">
      <div class="card-title">Session Label</div>
      <div class="row">
        <span class="row-label">Label</span>
        <input type="text" id="session-label" placeholder="e.g. outdoor-50m  /  line-of-sight-100m" style="width:320px">
      </div>
    </div>
    <div class="card">
      <div class="card-title">Test Pairs &nbsp;<span style="color:var(--muted);font-size:10px">Select source → destination</span></div>
      <div class="pairs-grid" id="pairs-grid">
        <div style="padding:12px;color:var(--muted);font-size:11px">Loading nodes...</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Test Types</div>
      <div class="tests-wrap">
        <label class="test-chip"><input type="checkbox" value="tcp_1stream"    checked> TCP 1-STREAM</label>
        <label class="test-chip"><input type="checkbox" value="tcp_4stream"          > TCP 4-STREAM</label>
        <label class="test-chip"><input type="checkbox" value="udp_throughput" checked> UDP THROUGHPUT</label>
        <label class="test-chip"><input type="checkbox" value="udp_jitter"           > UDP JITTER</label>
        <label class="test-chip"><input type="checkbox" value="packet_loss"          > PACKET LOSS</label>
        <label class="test-chip"><input type="checkbox" value="reverse"              > REVERSE</label>
        <label class="test-chip"><input type="checkbox" value="icmp_ping"      checked> ICMP PING</label>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Parameters</div>
      <div class="row">
        <span class="row-label">Duration</span>
        <input type="number" id="duration" value="30" min="5" max="300" style="width:80px">
        <span style="font-size:11px;color:var(--muted)">seconds</span>
      </div>
      <div class="row">
        <span class="row-label">UDP Bitrate</span>
        <select id="udp-bitrate">
          <option value="1M">1 Mbps</option>
          <option value="2M">2 Mbps</option>
          <option value="4M" selected>4 Mbps &nbsp;[HaLow typical max]</option>
          <option value="10M">10 Mbps</option>
          <option value="50M">50 Mbps</option>
          <option value="100M">100 Mbps</option>
        </select>
      </div>
    </div>
    <div style="padding:16px 0">
      <button class="btn btn-run" id="btn-run" onclick="startMeasurement()">&#9654; RUN MEASUREMENTS</button>
    </div>
    <div class="card" id="progress-card" style="display:none">
      <div class="card-title">Progress</div>
      <div class="progress-wrap">
        <div class="progress-bar-bg"><div class="progress-bar-fill" id="progress-fill"></div></div>
        <div class="progress-text" id="progress-text"></div>
      </div>
    </div>
  </div>

  <!-- ── SESSIONS ── -->
  <div id="tab-sessions" class="tab-pane" style="display:none">
    <div class="card">
      <div class="card-title">Saved Sessions</div>
      <div id="sessions-list">
        <div style="padding:16px;color:var(--muted);font-size:11px">Loading...</div>
      </div>
    </div>
  </div>

  <!-- ── UPLOAD ── -->
  <div id="tab-upload" class="tab-pane" style="display:none">
    <div class="card">
      <div class="card-title">Upload Results</div>
      <div class="upload-card">
        <div class="upload-info">
          <div class="upload-title">GitHub</div>
          <div class="upload-sub">mrleongalaxyum/manet-dev &rarr; measurements/ &nbsp;&bull;&nbsp; git commit + push</div>
        </div>
        <button class="btn btn-green" id="upload-github" onclick="uploadGithub()" disabled>PUSH</button>
      </div>
      <div class="upload-card">
        <div class="upload-info">
          <div class="upload-title">Ventum</div>
          <div class="upload-sub">rsync to colorado-governor.com</div>
        </div>
        <button class="btn btn-green" id="upload-ventum" onclick="uploadVentum()" disabled>UPLOAD</button>
      </div>
      <div style="padding:12px 16px;font-size:10px;color:var(--muted);letter-spacing:.5px">
        UPLOAD BUTTONS ENABLED ONLY WHEN INTERNET IS AVAILABLE
      </div>
    </div>
  </div>
</div>

<script>{JS}</script>
</body></html>"""

# ─────────────────────────────────────────────────────────────────────────────
# Request Handler
# ─────────────────────────────────────────────────────────────────────────────
class PerfHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access logs

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/') or '/'

        if path in ('/', '/index.html'):
            self.send_html(render_dashboard())

        elif path == '/api/topology':
            try:
                self.send_json(build_topology())
            except Exception as e:
                self.send_json({'error': str(e)}, 500)

        elif path == '/api/measure/status':
            with _measure_lock:
                self.send_json(dict(_measure_status))

        elif path == '/api/sessions':
            self.send_json(list_sessions())

        elif path.startswith('/api/sessions/'):
            parts = path[len('/api/sessions/'):].split('/')
            label = parts[0]
            if len(parts) > 1 and parts[1] == 'csv':
                csv_data = session_to_csv(label).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{label}.csv"')
                self.send_header('Content-Length', str(len(csv_data)))
                self.end_headers()
                self.wfile.write(csv_data)
            else:
                self.send_json(get_session_results(label))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')

    def do_POST(self):
        global _measure_status
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/') or '/'
        length = int(self.headers.get('Content-Length', 0))
        body   = self.rfile.read(length) if length else b'{}'

        if path == '/api/interface/toggle':
            try:
                req      = json.loads(body)
                node_ip  = req.get('node_ip', '')
                iface    = req.get('iface', '')
                state    = req.get('state', '')

                if node_ip == 'all':
                    nodes_raw = parse_registry()
                    errors = []
                    for nd in nodes_raw.values():
                        ip = nd.get('IPV4_ADDRESS', '')
                        if not ip:
                            continue
                        r = call_node_api(ip, '/api/control/interface', 'POST',
                                          {'iface': iface, 'state': state})
                        if not r.get('ok'):
                            errors.append(f"{ip}: {r.get('error')}")
                    if errors:
                        self.send_json({'ok': False, 'error': '; '.join(errors)})
                    else:
                        self.send_json({'ok': True})
                else:
                    r = call_node_api(node_ip, '/api/control/interface', 'POST',
                                      {'iface': iface, 'state': state})
                    self.send_json(r)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        elif path == '/api/txpower':
            try:
                req     = json.loads(body)
                node_ip = req.get('node_ip', '')
                iface   = req.get('iface', '')
                dbm     = req.get('dbm')
                r = call_node_api(node_ip, '/api/control/txpower', 'POST',
                                  {'iface': iface, 'dbm': dbm})
                self.send_json(r)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        elif path == '/api/halow/channel':
            try:
                req = json.loads(body)
                nodes_raw = parse_registry()
                errors = []
                for nd in nodes_raw.values():
                    ip = nd.get('IPV4_ADDRESS', '')
                    if not ip:
                        continue
                    r = call_node_api(ip, '/api/control/halow_channel', 'POST', req)
                    if not r.get('ok'):
                        errors.append(f"{ip}: {r.get('error')}")
                if errors:
                    self.send_json({'ok': False, 'error': '; '.join(errors)})
                else:
                    self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        elif path == '/api/measure/start':
            with _measure_lock:
                if _measure_status['running']:
                    self.send_json({'ok': False, 'error': 'Measurement already running'})
                    return
                try:
                    req    = json.loads(body)
                    label  = req.get('label', '').strip()
                    pairs  = req.get('pairs', [])
                    tests  = req.get('tests', [])
                    dur    = int(req.get('duration', 30))
                    bitrate = req.get('udp_bitrate', '4M')
                    if not label or not pairs or not tests:
                        self.send_json({'ok': False, 'error': 'Missing label, pairs, or tests'})
                        return
                    _measure_status['running']  = True
                    _measure_status['label']    = label
                    _measure_status['progress'] = 'Starting...'
                    _measure_status['error']    = ''
                    t = threading.Thread(
                        target=run_measurement_session,
                        args=(label, pairs, tests, dur, bitrate),
                        daemon=True
                    )
                    t.start()
                    self.send_json({'ok': True})
                except Exception as e:
                    _measure_status['running'] = False
                    self.send_json({'ok': False, 'error': str(e)})

        elif path == '/api/upload/github':
            try:
                repo_dir = '/home/radio/manet-dev'
                meas_src = SESSIONS_DIR
                meas_dst = os.path.join(repo_dir, 'measurements')
                subprocess.run(['rsync', '-a', meas_src + '/', meas_dst + '/'],
                               check=True, timeout=30)
                subprocess.run(['git', '-C', repo_dir, 'add', 'measurements/'],
                               check=True, timeout=10)
                ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                subprocess.run(['git', '-C', repo_dir, 'commit', '-m',
                                f'measurements: add results {ts}'],
                               check=True, timeout=10)
                subprocess.run(['git', '-C', repo_dir, 'push'],
                               check=True, timeout=30)
                self.send_json({'ok': True})
            except subprocess.CalledProcessError as e:
                self.send_json({'ok': False, 'error': str(e)})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        elif path == '/api/upload/ventum':
            try:
                conf = load_kv_file('/etc/mesh.conf')
                ventum_host = conf.get('ventum_host', 'colorado-governor.com')
                ventum_user = conf.get('ventum_user', 'manet')
                ventum_path = conf.get('ventum_path', '/var/www/measurements')
                subprocess.run(
                    ['rsync', '-avz', '-e', 'ssh -o StrictHostKeyChecking=no',
                     SESSIONS_DIR + '/', f'{ventum_user}@{ventum_host}:{ventum_path}/'],
                    check=True, timeout=60
                )
                self.send_json({'ok': True})
            except subprocess.CalledProcessError as e:
                self.send_json({'ok': False, 'error': str(e)})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')

# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

AVAHI_PERF_SERVICE = '/etc/avahi/services/perf-http.service'
AVAHI_PERF_CONTENT = """<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>MANET Perf Dashboard</name>
  <host-name>perf.local</host-name>
  <service>
    <type>_http._tcp</type>
    <port>8081</port>
  </service>
</service-group>
"""

def _is_gateway():
    return os.path.exists('/var/run/mesh-gateway.state')

def _manage_avahi_perf():
    """Run in background thread: install/remove avahi perf.local based on gateway status."""
    last = None
    while True:
        gw = _is_gateway()
        if gw != last:
            try:
                if gw:
                    with open(AVAHI_PERF_SERVICE, 'w') as f:
                        f.write(AVAHI_PERF_CONTENT)
                    subprocess.run(['systemctl', 'reload', 'avahi-daemon'], timeout=5, capture_output=True)
                else:
                    if os.path.exists(AVAHI_PERF_SERVICE):
                        os.remove(AVAHI_PERF_SERVICE)
                        subprocess.run(['systemctl', 'reload', 'avahi-daemon'], timeout=5, capture_output=True)
            except Exception:
                pass
            last = gw
        time.sleep(30)

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    t = threading.Thread(target=_manage_avahi_perf, daemon=True)
    t.start()

    server = ThreadedServer(('0.0.0.0', port), PerfHandler)
    print(f'MANET Perf Dashboard listening on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
