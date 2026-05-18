#!/bin/bash
# EC2 User-Data — runs once on first boot as root
set -e
exec > >(tee /var/log/user-data.log | logger -t user-data) 2>&1

echo "=== CloudStack Bootstrap START ==="

# ── 1. Update system ──────────────────────────────────────────────────────────
dnf update -y

# ── 2. Install deps ───────────────────────────────────────────────────────────
dnf install -y python3.11 python3.11-pip python3.11-devel \
               gcc mysql-devel ruby wget \
               amazon-cloudwatch-agent

# ── 3. Create app directory ───────────────────────────────────────────────────
mkdir -p /opt/app
useradd -r -s /sbin/nologin ec2-user 2>/dev/null || true
chown ec2-user:ec2-user /opt/app

# ── 4. Install CodeDeploy agent ───────────────────────────────────────────────
cd /tmp
wget -q https://aws-codedeploy-ap-south-1.s3.ap-south-1.amazonaws.com/latest/install
chmod +x ./install
./install auto
systemctl start codedeploy-agent
systemctl enable codedeploy-agent

# ── 5. Fetch AZ and Region from IMDS (v2) ─────────────────────────────────────
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
AZ=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/placement/availability-zone)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/placement/region)

# Write env file — picked up by systemd unit
cat > /etc/cloudstack.env <<EOF
AWS_REGION=${REGION}
AWS_AZ=${AZ}
DB_SECRET_NAME=prod/db/mysql-credentials
EOF

# ── 6. Configure CloudWatch Agent ─────────────────────────────────────────────
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CW'
{
  "metrics": {
    "namespace": "CloudStack/EC2",
    "metrics_collected": {
      "mem":  { "measurement": ["mem_used_percent"] },
      "disk": { "measurement": ["disk_used_percent"],
                "resources": ["/"] }
    },
    "append_dimensions": { "InstanceId": "${aws:InstanceId}" }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          { "file_path": "/var/log/user-data.log",
            "log_group_name":  "/cloudstack/user-data",
            "log_stream_name": "{instance_id}" },
          { "file_path": "/var/log/journal/cloudstack.log",
            "log_group_name":  "/cloudstack/app",
            "log_stream_name": "{instance_id}" }
        ]
      }
    }
  }
}
CW

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

echo "=== CloudStack Bootstrap COMPLETE ==="
