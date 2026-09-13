# WSL2 Development Environment Setup (Behind Corporate Firewall / Proxy)

This guide walks through configuring a local development environment using **WSL2 (Windows Subsystem for Linux)** and **Docker** behind a corporate firewall/proxy with corporate DNS and proxy filtering.

---

## 1. WSL2 DNS Resolution (`/etc/wsl.conf` & `/etc/resolv.conf`)

WSL2 automatically generates `/etc/resolv.conf` pointing to an internal Hyper-V virtual switch IP (e.g. `172.x.x.1`). In corporate environments, this often fails to resolve internal hostnames (such as internal proxy servers).

### A. Disable automatic `resolv.conf` generation
Edit `/etc/wsl.conf` (requires `sudo`):
```ini
[network]
generateResolvConf = false

[boot]
systemd=true
```

### B. Manually configure DNS server
Remove the existing symlink and set the corporate DNS server in `/etc/resolv.conf`:
```bash
sudo rm -f /etc/resolv.conf
sudo tee /etc/resolv.conf << 'EOF'
nameserver 10.11.20.70
EOF
```
*(Replace `10.11.20.70` with your organization's primary DNS server if different).*

---

## 2. Shell Environment & Proxy Variables

Set proxy variables in your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
# Corporate Proxy Configuration
export PROXY_SERVER="http://proxy.srv.bergenkom.no:8080"

export http_proxy="$PROXY_SERVER"
export https_proxy="$PROXY_SERVER"
export HTTP_PROXY="$PROXY_SERVER"
export HTTPS_PROXY="$PROXY_SERVER"

# Corporate & local bypass list
export no_proxy="localhost,127.0.0.1,host.docker.internal,.local,portico_masterdb,db,10.*,172.16.*,172.20.*,172.28.*,192.168.1.*,*.bergen.kommune.no,*.bergenkom.no"
export NO_PROXY="$no_proxy"
```

Apply the changes:
```bash
source ~/.bashrc
```

---

## 3. Package Manager Configuration (APT)

`sudo apt` does not always inherit shell proxy variables. Create `/etc/apt/apt.conf.d/90proxy`:

```bash
sudo tee /etc/apt/apt.conf.d/90proxy << 'EOF'
Acquire::http::Proxy "http://proxy.srv.bergenkom.no:8080";
Acquire::https::Proxy "http://proxy.srv.bergenkom.no:8080";
EOF
```

Test with:
```bash
sudo apt update
```

---

## 4. Git Proxy Configuration

If cloning or fetching repositories via HTTPS:

```bash
git config --global http.proxy http://proxy.srv.bergenkom.no:8080
git config --global https.proxy http://proxy.srv.bergenkom.no:8080
```

*(If using SSH keys with GitHub, ensure port 22 or SSH-over-HTTPS port 443 is permitted through the corporate firewall).*

---

## 5. Project Environment Settings (`.env.compose`)

Docker Compose reads `.env.compose` when building and running containers. Create or verify `.env.compose` in the repository root:

```ini
# Proxy configuration for Docker Compose builds and containers
http_proxy=http://proxy.srv.bergenkom.no:8080
https_proxy=http://proxy.srv.bergenkom.no:8080
no_proxy=localhost,127.0.0.1,host.docker.internal,portico_masterdb,db

# Database connection settings
DB_HOST=db
DB_PORT=5432
DB_NAME=masterdb
DB_USER=postgres
DB_PASSWORD=postgres
```

---

## 6. Docker Build & Network Notes

When building Docker images behind a corporate proxy:
- **`network: host` during build**: In [docker-compose.yml](docker-compose.yml), the build step uses `network: host`. This is required when corporate firewalls allow-list requests by the host's source IP (default Docker bridge NAT IPs may be dropped by the proxy).
- **PEAR / Extension installer proxy**: The [Dockerfile](Dockerfile) configures PHP PEAR and `install-php-extensions` to use the provided `http_proxy` build argument.

---

## 7. Corporate SSL Certificates (If Applicable)

If the firewall inspects TLS/SSL traffic:
1. Export the corporate root CA certificate from Windows (`certmgr.msc` -> Trusted Root Certification Authorities).
2. Copy it to `/usr/local/share/ca-certificates/` in WSL:
   ```bash
   sudo cp /mnt/c/path/to/corporate-ca.crt /usr/local/share/ca-certificates/
   sudo update-ca-certificates
   ```

---

## 8. Running and Testing the Stack

```bash
# 1. Build images
docker compose build

# 2. Start services
docker compose up -d

# 3. Check status
docker compose ps
```

- **Swagger UI**: <http://localhost:8083/swagger.html>
- **Redoc UI**: <http://localhost:8083/redoc.html>
- **Database (pgAdmin / Host)**:
  - **Host**: `localhost`
  - **Port**: `5432`
  - **User**: `postgres`
  - **Password**: `postgres`
  - **Database**: `masterdb`

```

3. Restart WSL from PowerShell:
   ```powershell
   wsl --shutdown
   ```

---

## 6. Running the Stack

Once proxy and environment settings are in place:

```bash
# Build containers with proxy arguments
docker compose build

# Start services (PostgreSQL 18 database + PHP/Apache API)
docker compose up -d

# Verify services
docker compose ps
```

- **Swagger UI**: <http://localhost:8083/swagger.html>
- **Redoc UI**: <http://localhost:8083/redoc.html>
- **Database (via pgAdmin / Host)**: Host: `localhost`, Port: `5432`, User: `postgres`, Password: `postgres`, DB: `masterdb`
