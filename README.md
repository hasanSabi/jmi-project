# CloudStack — Cloud-Native 3-Tier Scalable Web Platform

> MCA Major Project · Jamia Millia Islamia · 2026  
> Stack: Python (Flask) + MySQL · AWS ap-south-1 (Mumbai)

## Architecture

```
Internet
   │
   ▼
[Application Load Balancer]  ← public subnets (10.0.1.0/24, 10.0.2.0/24)
   │
   ▼
[EC2 Auto Scaling Group]     ← private subnets (10.0.3.0/24, 10.0.4.0/24)
  Flask + Gunicorn
   │
   ▼
[Amazon RDS MySQL 8.0]       ← db subnets (10.0.5.0/24, 10.0.6.0/24)
  Multi-AZ
```

## Project Structure

```
project/
├── app/
│   ├── app.py                # Flask application
│   ├── templates/
│   │   └── index.html        # Minimal dark UI
│   ├── requirements.txt
│   ├── gunicorn.conf.py
│   └── cloudstack.service    # systemd unit
├── scripts/
│   ├── before_install.sh     # CodeDeploy lifecycle hooks
│   ├── after_install.sh
│   ├── start_app.sh
│   └── validate.sh
├── infrastructure/
│   └── user-data.sh          # EC2 bootstrap script
├── .github/
│   └── workflows/
│       └── deploy.yml        # GitHub Actions CI/CD
├── appspec.yml               # CodeDeploy spec
├── DEPLOYMENT_GUIDE.md       # Full step-by-step guide ← START HERE
└── README.md
```

## Quick Start

See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for the complete step-by-step guide.

## Local Development

```bash
# Install deps
cd app
pip install -r requirements.txt

# Run with local MySQL
export DB_HOST=127.0.0.1
export DB_USER=root
export DB_PASS=yourpassword
export DB_NAME=appdb

python app.py
# Open http://localhost:5000
```
