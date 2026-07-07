# Deployment Guide — ETL Platform v1.0.0

Copy-paste commands for every deployment target. Each section starts from a clean machine.

---

## Windows (Local Development)

```powershell
# 1. Clone
git clone https://github.com/your-org/etl-platform.git
cd etl-platform

# 2. Create venv
python -m venv .venv
.venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
copy .env.example .env
# Edit .env in Notepad — set SECRET_KEY, JWT_SECRET, API_KEY_SALT
# DATABASE_URL=postgresql+psycopg2://etl_user:etl_password@localhost:5432/etl_platform

# 5. Start PostgreSQL via Docker
docker run -d --name etl_postgres ^
  -e POSTGRES_USER=etl_user ^
  -e POSTGRES_PASSWORD=etl_password ^
  -e POSTGRES_DB=etl_platform ^
  -p 5432:5432 postgres:15-alpine

# 6. Setup DB + start
python scripts/setup_database.py
python main.py
```

---

## Ubuntu / Debian Linux (Local or VM)

```bash
# 1. Install Python 3.12
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git

# 2. Clone
git clone https://github.com/your-org/etl-platform.git
cd etl-platform

# 3. Virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 4. Install
pip install -r requirements.txt

# 5. Configure
cp .env.example .env
# Generate secrets:
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Edit .env with your values

# 6. Install & start PostgreSQL
sudo apt install -y postgresql-15
sudo -u postgres psql -c "CREATE USER etl_user WITH PASSWORD 'etl_password';"
sudo -u postgres psql -c "CREATE DATABASE etl_platform OWNER etl_user;"

# 7. Setup & start
python scripts/setup_database.py
python main.py &
streamlit run dashboard/Home.py &
```

---

## Docker Compose (Any OS)

**Requires:** Docker 24+ and Docker Compose v2.

```bash
# 1. Clone
git clone https://github.com/your-org/etl-platform.git
cd etl-platform

# 2. Configure
cp .env.example .env
# REQUIRED — edit these three lines in .env:
#   SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
#   JWT_SECRET=<generate again>
#   DB_PASSWORD=choose_a_strong_password

# 3. Start
docker-compose -f docker-compose.prod.yml up -d

# 4. Initialize DB (first run only)
docker-compose -f docker-compose.prod.yml exec api python scripts/setup_database.py

# 5. Verify
curl http://localhost:8000/api/v1/health/ping
# Open http://localhost:8501 — login: admin / Admin1234!
```

---

## AWS EC2 (Ubuntu 22.04)

```bash
# --- On your local machine: launch EC2 ---
# AMI: Ubuntu 22.04 LTS, type: t3.medium (min), ports: 22, 80, 8000, 8501

# --- SSH into EC2 ---
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>

# Install Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker ubuntu
newgrp docker

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Clone and configure
git clone https://github.com/your-org/etl-platform.git
cd etl-platform
cp .env.example .env
nano .env   # Set SECRET_KEY, JWT_SECRET, DB_PASSWORD, CORS_ORIGINS=http://<EC2_IP>

# Start
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec api python scripts/setup_database.py

# Access:
# API:       http://<EC2_IP>:8000/docs
# Dashboard: http://<EC2_IP>:80
```

**Security Group ports to open:**
- 22 (SSH — your IP only)
- 80 (HTTP — 0.0.0.0/0)
- 443 (HTTPS — 0.0.0.0/0, when TLS configured)
- 8000 (optional direct API access)
- 8501 (optional direct dashboard access)

---

## DigitalOcean Droplet (Ubuntu 22.04)

Same as AWS EC2 above. Use a 2 GB RAM / 2 CPU Droplet ($18/month) minimum.

```bash
# After SSH:
# 1. Install Docker (same as AWS)
# 2. Configure firewall:
sudo ufw allow 22 80 443 8000 8501
sudo ufw enable

# 3. Follow Docker Compose steps above
```

---

## Oracle Cloud Free Tier (ARM Ubuntu)

```bash
# Free tier: 4 OCPUs, 24 GB RAM — more than enough
# Ingress rules: allow TCP 80, 443, 8000, 8501

# Install Docker (ARM compatible)
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker opc && newgrp docker

# Same steps as AWS EC2 above
```

---

## Production Checklist

Before going to production, verify:

```bash
# 1. No placeholder secrets
grep -E "change-this|change-me|changeme" .env && echo "WARNING: Update secrets!"

# 2. Production environment set
grep "APP_ENV=production" .env

# 3. Secure passwords
grep "Admin1234!" .env && echo "WARNING: Change default passwords!"

# 4. Correct CORS origins (not localhost)
grep "CORS_ORIGINS" .env

# 5. JSON logging enabled
grep "LOG_JSON_FORMAT=True" .env
```

**Production .env changes:**
```dotenv
APP_ENV=production
LOG_JSON_FORMAT=True
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=True
DB_ECHO=False
PIPELINE_ENABLE_SCHEDULER=True
CORS_ORIGINS=https://your-actual-domain.com
```

---

## Kubernetes Deployment

```bash
# 1. Update k8s/secret.yaml with base64-encoded real values
#    echo -n 'your-secret' | base64
nano k8s/secret.yaml

# 2. Apply manifests in order
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/service-api.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/network-policy.yaml

# 3. Check
kubectl get pods -n etl-platform
kubectl logs -n etl-platform deployment/etl-platform-api

# 4. Initialize DB
kubectl exec -n etl-platform deployment/etl-platform-api -- \
  python scripts/setup_database.py
```

---

## TLS / HTTPS Setup (Production)

Using Let's Encrypt with Certbot:

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate (replace with your domain)
sudo certbot --nginx -d etl-platform.yourdomain.com

# Certbot auto-renews. Verify:
sudo certbot renew --dry-run
```

Update `docker/nginx/nginx.prod.conf` to add the SSL server block and update `CORS_ORIGINS` in `.env`.

---

## Backup Setup (Cron)

```bash
# Add to crontab (daily at 3 AM):
crontab -e
# Add:
0 3 * * * cd /path/to/etl-platform && bash scripts/backup/backup_db.sh >> logs/backup.log 2>&1
0 4 * * 0 cd /path/to/etl-platform && bash scripts/backup/backup_config.sh >> logs/backup.log 2>&1
```
