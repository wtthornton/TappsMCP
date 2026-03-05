# VPN and Mesh Networking

## Tailscale

Tailscale builds a WireGuard-based mesh network with zero configuration:

### ACL Policy

Define access rules in `policy.json` (Tailscale admin console or GitOps):

```json
{
  "acls": [
    { "action": "accept", "src": ["group:engineering"], "dst": ["tag:prod:443"] },
    { "action": "accept", "src": ["group:engineering"], "dst": ["tag:staging:*"] },
    { "action": "accept", "src": ["tag:monitoring"], "dst": ["*:9090", "*:9100"] }
  ],
  "groups": {
    "group:engineering": ["user1@example.com", "user2@example.com"],
    "group:ops": ["ops1@example.com"]
  },
  "tagOwners": {
    "tag:prod": ["group:ops"],
    "tag:staging": ["group:engineering"],
    "tag:monitoring": ["group:ops"]
  },
  "autoApprovers": {
    "routes": {
      "10.0.0.0/8": ["tag:subnet-router"]
    }
  }
}
```

### Subnet Routers

Expose entire subnets to the Tailscale network:

```bash
# On the subnet router node
tailscale up --advertise-routes=10.0.1.0/24,10.0.2.0/24 --accept-dns=false

# Other nodes auto-discover the routes (if approved)
tailscale status  # shows subnet routes
```

### Exit Nodes

Route all traffic through a specific node (VPN mode):

```bash
# On the exit node
tailscale up --advertise-exit-node

# On the client
tailscale up --exit-node=exit-node-hostname
tailscale up --exit-node=  # disable exit node
```

### Split Tunneling

Only route specific traffic through Tailscale:

```bash
# Default: split tunneling is ON (only tailnet traffic goes through Tailscale)
# To route ALL traffic through exit node:
tailscale up --exit-node=mynode --exit-node-allow-lan-access
```

## WireGuard

WireGuard is the underlying protocol for modern VPN solutions:

### Configuration

```ini
# /etc/wireguard/wg0.conf - Server
[Interface]
PrivateKey = <server-private-key>
Address = 10.200.0.1/24
ListenPort = 51820
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
PublicKey = <client-public-key>
AllowedIPs = 10.200.0.2/32

# Client
[Interface]
PrivateKey = <client-private-key>
Address = 10.200.0.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = <server-public-key>
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0          # Route all traffic (full tunnel)
# AllowedIPs = 10.200.0.0/24    # Route only VPN subnet (split tunnel)
PersistentKeepalive = 25
```

### Key Generation

```bash
wg genkey | tee privatekey | wg pubkey > publickey
wg genpsk > presharedkey  # optional additional security
```

### Management

```bash
wg-quick up wg0       # start interface
wg-quick down wg0     # stop interface
wg show               # show status and stats
```

## Zero-Trust Networking Principles

1. **Never trust, always verify** - authenticate every connection regardless of network location
2. **Least privilege access** - grant minimum permissions needed per service/user
3. **Micro-segmentation** - isolate workloads so lateral movement is blocked
4. **Continuous verification** - re-evaluate trust based on device posture and behavior
5. **Encrypt everything** - all traffic encrypted, even internal east-west traffic

### Implementation Checklist

- Use mutual TLS (mTLS) between services
- Implement identity-aware proxies (e.g., Tailscale, Cloudflare Access, Pomerium)
- Tag and segment resources by sensitivity level
- Monitor and alert on unusual access patterns
- Rotate credentials and certificates automatically
- Use short-lived tokens instead of long-lived API keys

## Network Topology Comparison

| Feature | Tailscale | WireGuard (manual) | OpenVPN |
|---|---|---|---|
| Setup complexity | Low (SaaS) | Medium | High |
| Protocol | WireGuard | WireGuard | TLS/UDP |
| NAT traversal | Automatic (DERP) | Manual | Manual |
| Mesh networking | Built-in | Manual config | Hub-spoke |
| Performance | Near wire-speed | Near wire-speed | ~60-80% |
| ACL management | Centralized UI/API | iptables | Server config |
