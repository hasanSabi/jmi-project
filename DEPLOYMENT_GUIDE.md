# CloudStack — Complete Deployment Guide
### Cloud-Native 3-Tier Scalable Web Platform on AWS
**Stack:** Python (Flask) + MySQL · Ubuntu/Debian local · AWS ap-south-1 (Mumbai)

---

## Prerequisites Checklist

Before starting, confirm the following:

| Item | Requirement |
|---|---|
| AWS Account | Active account with billing enabled |
| AWS CLI | v2.x installed and configured (`aws configure`) |
| IAM User | Has AdministratorAccess (for this project setup) |
| Local OS | Ubuntu / Debian with `sudo` access |
| Git | Installed locally |
| GitHub | Account with a new **empty** repository created |

Verify your CLI is working:
```bash
aws sts get-caller-identity
# Should return your Account ID, UserId, and ARN
```

---

## Part 1 — IAM Setup

> All IAM resources are created first. Everything else depends on them.

### Step 1.1 — Create the EC2 Instance Role

```bash
# Create the trust policy document
cat > /tmp/ec2-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create the role
aws iam create-role \
  --role-name ec2-app-role \
  --assume-role-policy-document file:///tmp/ec2-trust.json \
  --description "Role for CloudStack EC2 application instances"
```

### Step 1.2 — Attach Managed Policies to EC2 Role

```bash
# SSM Session Manager (replaces SSH)
aws iam attach-role-policy \
  --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

# CloudWatch Agent
aws iam attach-role-policy \
  --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# CodeDeploy (so agent can register and receive deployments)
aws iam attach-role-policy \
  --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforAWSCodeDeploy
```

### Step 1.3 — Add Secrets Manager Inline Policy

```bash
# Get your account ID first
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": "arn:aws:secretsmanager:ap-south-1:${ACCOUNT_ID}:secret:prod/db/mysql-credentials*"
  }]
}
EOF

aws iam put-role-policy \
  --role-name ec2-app-role \
  --policy-name SecretsManagerRead \
  --policy-document file:///tmp/secrets-policy.json
```

### Step 1.4 — Create EC2 Instance Profile

```bash
aws iam create-instance-profile \
  --instance-profile-name ec2-app-profile

aws iam add-role-to-instance-profile \
  --instance-profile-name ec2-app-profile \
  --role-name ec2-app-role
```

### Step 1.5 — Create CodeDeploy Service Role

```bash
cat > /tmp/codedeploy-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "codedeploy.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name codedeploy-service-role \
  --assume-role-policy-document file:///tmp/codedeploy-trust.json

aws iam attach-role-policy \
  --role-name codedeploy-service-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSCodeDeployRole
```

---

## Part 2 — VPC and Networking

### Step 2.1 — Create the VPC

```bash
VPC_ID=$(aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --region ap-south-1 \
  --query 'Vpc.VpcId' --output text)

aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-support

aws ec2 create-tags --resources $VPC_ID \
  --tags Key=Name,Value=cloudstack-vpc

echo "VPC ID: $VPC_ID"
# SAVE THIS — you'll need it throughout
```

### Step 2.2 — Create Internet Gateway

```bash
IGW_ID=$(aws ec2 create-internet-gateway \
  --query 'InternetGateway.InternetGatewayId' --output text)

aws ec2 attach-internet-gateway \
  --internet-gateway-id $IGW_ID \
  --vpc-id $VPC_ID

aws ec2 create-tags --resources $IGW_ID \
  --tags Key=Name,Value=cloudstack-igw

echo "IGW ID: $IGW_ID"
```

### Step 2.3 — Create 6 Subnets

```bash
# Public Subnet — AZ: ap-south-1a
PUB_1A=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 \
  --availability-zone ap-south-1a \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $PUB_1A --tags Key=Name,Value=public-subnet-1a

# Public Subnet — AZ: ap-south-1b
PUB_1B=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 \
  --availability-zone ap-south-1b \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $PUB_1B --tags Key=Name,Value=public-subnet-1b

# Private Subnet — ap-south-1a (application)
PRIV_1A=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.3.0/24 \
  --availability-zone ap-south-1a \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $PRIV_1A --tags Key=Name,Value=private-subnet-1a

# Private Subnet — ap-south-1b (application)
PRIV_1B=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.4.0/24 \
  --availability-zone ap-south-1b \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $PRIV_1B --tags Key=Name,Value=private-subnet-1b

# DB Subnet — ap-south-1a
DB_1A=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.5.0/24 \
  --availability-zone ap-south-1a \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $DB_1A --tags Key=Name,Value=db-subnet-1a

# DB Subnet — ap-south-1b
DB_1B=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID --cidr-block 10.0.6.0/24 \
  --availability-zone ap-south-1b \
  --query 'Subnet.SubnetId' --output text)
aws ec2 create-tags --resources $DB_1B --tags Key=Name,Value=db-subnet-1b

echo "Public:  $PUB_1A  $PUB_1B"
echo "Private: $PRIV_1A  $PRIV_1B"
echo "DB:      $DB_1A  $DB_1B"
```

### Step 2.4 — Enable Auto-Assign Public IP on Public Subnets

```bash
aws ec2 modify-subnet-attribute \
  --subnet-id $PUB_1A --map-public-ip-on-launch

aws ec2 modify-subnet-attribute \
  --subnet-id $PUB_1B --map-public-ip-on-launch
```

### Step 2.5 — Public Route Table

```bash
PUB_RT=$(aws ec2 create-route-table \
  --vpc-id $VPC_ID --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-tags --resources $PUB_RT --tags Key=Name,Value=public-rt

# Default route → Internet Gateway
aws ec2 create-route \
  --route-table-id $PUB_RT \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate with both public subnets
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_1A
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_1B

echo "Public RT: $PUB_RT"
```

### Step 2.6 — NAT Gateway (in public-subnet-1a)

```bash
# Allocate Elastic IP
EIP_ALLOC=$(aws ec2 allocate-address \
  --domain vpc --query 'AllocationId' --output text)

# Create NAT Gateway
NAT_ID=$(aws ec2 create-nat-gateway \
  --subnet-id $PUB_1A \
  --allocation-id $EIP_ALLOC \
  --query 'NatGateway.NatGatewayId' --output text)
aws ec2 create-tags --resources $NAT_ID --tags Key=Name,Value=cloudstack-nat

echo "NAT Gateway: $NAT_ID — waiting for it to become available..."
aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT_ID
echo "NAT Gateway is available."
```

### Step 2.7 — Private Route Table (for application subnets)

```bash
PRIV_RT=$(aws ec2 create-route-table \
  --vpc-id $VPC_ID --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-tags --resources $PRIV_RT --tags Key=Name,Value=private-rt

# Default route → NAT Gateway
aws ec2 create-route \
  --route-table-id $PRIV_RT \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id $NAT_ID

# Associate with both private subnets
aws ec2 associate-route-table --route-table-id $PRIV_RT --subnet-id $PRIV_1A
aws ec2 associate-route-table --route-table-id $PRIV_RT --subnet-id $PRIV_1B

echo "Private RT: $PRIV_RT"
```

> **Note:** DB subnets use only the VPC default route table (local traffic only). No action needed.

---

## Part 3 — Security Groups

### Step 3.1 — ALB Security Group

```bash
ALB_SG=$(aws ec2 create-security-group \
  --group-name alb-sg \
  --description "CloudStack ALB - internet-facing" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 create-tags --resources $ALB_SG --tags Key=Name,Value=alb-sg

# Allow HTTP from internet (for project demo — no HTTPS/ACM needed)
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG \
  --protocol tcp --port 80 --cidr 0.0.0.0/0

echo "ALB SG: $ALB_SG"
```

### Step 3.2 — App Security Group

```bash
APP_SG=$(aws ec2 create-security-group \
  --group-name app-sg \
  --description "CloudStack EC2 application instances" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 create-tags --resources $APP_SG --tags Key=Name,Value=app-sg

# Allow port 5000 ONLY from the ALB security group
aws ec2 authorize-security-group-ingress \
  --group-id $APP_SG \
  --protocol tcp --port 5000 \
  --source-group $ALB_SG

# Allow all outbound (for SSM, pip, boto3, etc.)
# Outbound is open by default — no action needed.

echo "App SG: $APP_SG"
```

### Step 3.3 — RDS Security Group

```bash
RDS_SG=$(aws ec2 create-security-group \
  --group-name rds-sg \
  --description "CloudStack RDS MySQL" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 create-tags --resources $RDS_SG --tags Key=Name,Value=rds-sg

# Allow MySQL ONLY from app instances
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG \
  --protocol tcp --port 3306 \
  --source-group $APP_SG

echo "RDS SG: $RDS_SG"
```

---

## Part 4 — Secrets Manager (DB credentials)

```bash
# Generate a strong password
DB_PASS=$(openssl rand -base64 20 | tr -d '/+=')
DB_USER="appuser"
DB_NAME="appdb"

# We'll fill in the RDS host after creating the DB (Step 5)
# For now, store everything except the host
aws secretsmanager create-secret \
  --name prod/db/mysql-credentials \
  --region ap-south-1 \
  --description "CloudStack RDS MySQL credentials" \
  --secret-string "{
    \"username\": \"${DB_USER}\",
    \"password\": \"${DB_PASS}\",
    \"dbname\":   \"${DB_NAME}\",
    \"host\":     \"PLACEHOLDER\"
  }"

echo ""
echo "=== SAVE THESE — you will need them ==="
echo "DB_USER: $DB_USER"
echo "DB_PASS: $DB_PASS"
echo "DB_NAME: $DB_NAME"
echo "======================================="
```

---

## Part 5 — Amazon RDS MySQL (Multi-AZ)

### Step 5.1 — Create DB Subnet Group

```bash
aws rds create-db-subnet-group \
  --db-subnet-group-name cloudstack-db-subnet-group \
  --db-subnet-group-description "CloudStack DB subnets" \
  --subnet-ids $DB_1A $DB_1B
```

### Step 5.2 — Launch RDS Instance

> This takes 5–10 minutes. Run it and move to the next part while it provisions.

```bash
# Use the DB_PASS variable you generated in Step 4
aws rds create-db-instance \
  --db-instance-identifier cloudstack-db \
  --db-instance-class db.t3.micro \
  --engine mysql \
  --engine-version 8.0 \
  --master-username admin \
  --master-user-password "$DB_PASS" \
  --allocated-storage 20 \
  --storage-type gp2 \
  --multi-az \
  --db-subnet-group-name cloudstack-db-subnet-group \
  --vpc-security-group-ids $RDS_SG \
  --db-name appdb \
  --backup-retention-period 7 \
  --no-publicly-accessible \
  --deletion-protection \
  --region ap-south-1

echo "RDS is being created. Continue to Part 6."
echo "Check status with: aws rds describe-db-instances \\"
echo "  --db-instance-identifier cloudstack-db \\"
echo "  --query 'DBInstances[0].DBInstanceStatus'"
```

### Step 5.3 — Get RDS Endpoint and Update Secret

```bash
# Run this only after RDS status becomes "available" (5-10 min)
aws rds wait db-instance-available \
  --db-instance-identifier cloudstack-db

RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier cloudstack-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)

echo "RDS Endpoint: $RDS_ENDPOINT"

# Update the secret with the real host
aws secretsmanager update-secret \
  --secret-id prod/db/mysql-credentials \
  --secret-string "{
    \"username\": \"${DB_USER}\",
    \"password\": \"${DB_PASS}\",
    \"dbname\":   \"${DB_NAME}\",
    \"host\":     \"${RDS_ENDPOINT}\"
  }"

echo "Secret updated with RDS endpoint."
```

### Step 5.4 — Create the application DB user

> Connect to RDS via a temporary EC2 jump instance, or use SSM after EC2 is running.
> For now, create the `appuser` account with a SQL command.

After your first EC2 instance is running (Part 7), run:

```bash
# From your local machine, start an SSM session to an EC2 instance
aws ssm start-session --target <INSTANCE_ID> --region ap-south-1

# Inside the session, install MySQL client and create the user
sudo dnf install -y mysql

mysql -h $RDS_ENDPOINT -u admin -p"$DB_PASS" <<'SQL'
CREATE DATABASE IF NOT EXISTS appdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'appuser'@'%' IDENTIFIED BY 'SAME_DB_PASS_HERE';
GRANT ALL PRIVILEGES ON appdb.* TO 'appuser'@'%';
FLUSH PRIVILEGES;
SQL
```

---

## Part 6 — Application Load Balancer

### Step 6.1 — Create the ALB

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name cloudstack-alb \
  --subnets $PUB_1A $PUB_1B \
  --security-groups $ALB_SG \
  --scheme internet-facing \
  --type application \
  --ip-address-type ipv4 \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' --output text)

echo "ALB ARN: $ALB_ARN"
echo "ALB DNS (your app URL): http://$ALB_DNS"
# SAVE THE DNS NAME — this is your application URL
```

### Step 6.2 — Create Target Group

```bash
TG_ARN=$(aws elbv2 create-target-group \
  --name cloudstack-targets \
  --protocol HTTP \
  --port 5000 \
  --vpc-id $VPC_ID \
  --target-type instance \
  --health-check-protocol HTTP \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --health-check-timeout-seconds 5 \
  --matcher HttpCode=200 \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "Target Group ARN: $TG_ARN"
```

### Step 6.3 — Create HTTP Listener

```bash
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN
```

---

## Part 7 — Launch Template and Auto Scaling Group

### Step 7.1 — Get the Amazon Linux 2023 AMI ID

```bash
AMI_ID=$(aws ec2 describe-images \
  --owners amazon \
  --filters \
    "Name=name,Values=al2023-ami-2023*-x86_64" \
    "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' \
  --output text \
  --region ap-south-1)

echo "AMI ID: $AMI_ID"
```

### Step 7.2 — Encode User-Data

```bash
USER_DATA=$(base64 -w 0 infrastructure/user-data.sh)
```

### Step 7.3 — Create Launch Template

```bash
LT_ID=$(aws ec2 create-launch-template \
  --launch-template-name cloudstack-lt \
  --version-description "v1" \
  --launch-template-data "{
    \"ImageId\": \"${AMI_ID}\",
    \"InstanceType\": \"t3.micro\",
    \"IamInstanceProfile\": {\"Name\": \"ec2-app-profile\"},
    \"SecurityGroupIds\": [\"${APP_SG}\"],
    \"UserData\": \"${USER_DATA}\",
    \"TagSpecifications\": [{
      \"ResourceType\": \"instance\",
      \"Tags\": [{\"Key\": \"Name\", \"Value\": \"cloudstack-app\"}]
    }]
  }" \
  --query 'LaunchTemplate.LaunchTemplateId' --output text)

echo "Launch Template ID: $LT_ID"
```

### Step 7.4 — Create Auto Scaling Group

```bash
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name cloudstack-asg \
  --launch-template LaunchTemplateId=$LT_ID,Version='$Latest' \
  --min-size 2 \
  --max-size 6 \
  --desired-capacity 2 \
  --vpc-zone-identifier "${PRIV_1A},${PRIV_1B}" \
  --target-group-arns $TG_ARN \
  --health-check-type ELB \
  --health-check-grace-period 300 \
  --tags Key=Name,Value=cloudstack-app,PropagateAtLaunch=true
```

### Step 7.5 — Add Target Tracking Scaling Policy (CPU 70%)

```bash
aws autoscaling put-scaling-policy \
  --auto-scaling-group-name cloudstack-asg \
  --policy-name cloudstack-cpu-tracking \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ASGAverageCPUUtilization"
    },
    "TargetValue": 70.0,
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }'
```

### Step 7.6 — Verify instances are launching

```bash
# Wait ~3 minutes, then check
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names cloudstack-asg \
  --query 'AutoScalingGroups[0].Instances[*].{ID:InstanceId,State:LifecycleState,Health:HealthStatus,AZ:AvailabilityZone}' \
  --output table
```

---

## Part 8 — Push Application Code to GitHub + First Deployment

### Step 8.1 — Initialize Git repository locally

```bash
cd project/   # the root of the project folder you cloned/created
git init
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

### Step 8.2 — Create S3 Bucket for deployment artefacts

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="cloudstack-deploy-${ACCOUNT_ID}"

aws s3 mb s3://$BUCKET_NAME --region ap-south-1

aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled

echo "Deployment bucket: $BUCKET_NAME"
# SAVE this name
```

### Step 8.3 — Create CodeDeploy Application and Deployment Group

```bash
CODEDEPLOY_ROLE_ARN=$(aws iam get-role \
  --role-name codedeploy-service-role \
  --query 'Role.Arn' --output text)

# Create application
aws deploy create-application \
  --application-name CloudStack \
  --compute-platform Server

# Create deployment group targeting the ASG
aws deploy create-deployment-group \
  --application-name CloudStack \
  --deployment-group-name CloudStack-DeploymentGroup \
  --service-role-arn $CODEDEPLOY_ROLE_ARN \
  --auto-scaling-groups cloudstack-asg \
  --load-balancer-info "TargetGroupInfoList=[{Name=cloudstack-targets}]" \
  --deployment-config-name CodeDeployDefault.OneAtATime \
  --auto-rollback-configuration enabled=true,events=DEPLOYMENT_FAILURE
```

### Step 8.4 — Set up GitHub Actions OIDC with AWS

```bash
# Create OIDC identity provider for GitHub
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GITHUB_USER="YOUR_GITHUB_USERNAME"    # ← replace
GITHUB_REPO="YOUR_GITHUB_REPO_NAME"  # ← replace

# Trust policy for GitHub Actions
cat > /tmp/github-trust.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:${GITHUB_USER}/${GITHUB_REPO}:*"
      }
    }
  }]
}
EOF

# Create the role
GH_ROLE_ARN=$(aws iam create-role \
  --role-name github-actions-deploy-role \
  --assume-role-policy-document file:///tmp/github-trust.json \
  --query 'Role.Arn' --output text)

# Permissions: CodeDeploy + S3 uploads only
cat > /tmp/github-perms.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "deploy:CreateDeployment",
        "deploy:GetDeployment",
        "deploy:GetDeploymentConfig",
        "deploy:RegisterApplicationRevision",
        "deploy:GetApplicationRevision"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name github-actions-deploy-role \
  --policy-name DeployPolicy \
  --policy-document file:///tmp/github-perms.json

echo ""
echo "=== Add these as GitHub Repository Secrets ==="
echo "AWS_DEPLOY_ROLE_ARN = $GH_ROLE_ARN"
echo "DEPLOY_BUCKET       = $BUCKET_NAME"
echo "=============================================="
```

### Step 8.5 — Add GitHub Secrets

In your GitHub repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** and add:
   - `AWS_DEPLOY_ROLE_ARN` = the ARN from the command above
   - `DEPLOY_BUCKET` = the S3 bucket name

### Step 8.6 — Push code and trigger first deployment

```bash
git add .
git commit -m "feat: initial CloudStack deployment"
git branch -M main
git push -u origin main
```

Go to your GitHub repository → **Actions** tab → watch the workflow run.

---

## Part 9 — Verify Everything is Working

### Step 9.1 — Check ALB health

```bash
# Get ALB DNS if you don't have it
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names cloudstack-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

# Check health endpoint
curl http://$ALB_DNS/health
# Expected: {"db": "ok", "host": "ip-10-0-x-x.ap-south-1.compute.internal", "status": "ok"}

# Open the app
echo "Open in browser: http://$ALB_DNS"
```

### Step 9.2 — Check target group health

```bash
TG_ARN=$(aws elbv2 describe-target-groups \
  --names cloudstack-targets \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

aws elbv2 describe-target-health \
  --target-group-arn $TG_ARN \
  --query 'TargetHealthDescriptions[*].{Target:Target.Id,State:TargetHealth.State}' \
  --output table
# Both instances should show: healthy
```

### Step 9.3 — Connect to an instance via SSM (no SSH needed)

```bash
# Get an instance ID from the ASG
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names cloudstack-asg \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

# Start session
aws ssm start-session \
  --target $INSTANCE_ID \
  --region ap-south-1
```

### Step 9.4 — Verify RDS connection from inside instance

```bash
# Inside the SSM session:
sudo systemctl status cloudstack

# Check app logs
sudo journalctl -u cloudstack -n 50 --no-pager

# Test DB connection directly
curl http://localhost:5000/health
```

---

## Part 10 — CloudWatch Observability

### Step 10.1 — Create SNS Topic for Alerts

```bash
SNS_ARN=$(aws sns create-topic \
  --name cloudstack-alerts \
  --query 'TopicArn' --output text)

# Subscribe your email
aws sns subscribe \
  --topic-arn $SNS_ARN \
  --protocol email \
  --notification-endpoint your-email@example.com

echo "Check your email and confirm the subscription."
```

### Step 10.2 — Create CloudWatch Alarms

```bash
# High CPU alarm (also triggers ASG scale-out via the scaling policy)
aws cloudwatch put-metric-alarm \
  --alarm-name "CloudStack-HighCPU" \
  --alarm-description "Average CPU > 70% for 2 consecutive minutes" \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=AutoScalingGroupName,Value=cloudstack-asg \
  --statistic Average \
  --period 60 \
  --evaluation-periods 2 \
  --threshold 70 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions $SNS_ARN

# ALB 5XX errors
ALB_SUFFIX=$(echo $ALB_ARN | sed 's|.*:loadbalancer/||')
aws cloudwatch put-metric-alarm \
  --alarm-name "CloudStack-5XX-Errors" \
  --alarm-description "ALB 5XX errors > 10 per minute" \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=$ALB_SUFFIX \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions $SNS_ARN

echo "CloudWatch alarms created."
```

### Step 10.3 — Enable VPC Flow Logs

```bash
# Create CloudWatch Log Group for flow logs
aws logs create-log-group \
  --log-group-name /vpc/cloudstack-flowlogs \
  --region ap-south-1

# Create Flow Logs IAM role
cat > /tmp/flowlogs-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "vpc-flow-logs.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name vpc-flow-logs-role \
  --assume-role-policy-document file:///tmp/flowlogs-trust.json

aws iam put-role-policy \
  --role-name vpc-flow-logs-role \
  --policy-name FlowLogsPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
      "Resource": "*"
    }]
  }'

FLOWLOGS_ROLE=$(aws iam get-role \
  --role-name vpc-flow-logs-role \
  --query 'Role.Arn' --output text)

aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids $VPC_ID \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name /vpc/cloudstack-flowlogs \
  --deliver-logs-permission-arn $FLOWLOGS_ROLE

echo "VPC Flow Logs enabled."
```

---

## Part 11 — Test High Availability

### Test A — RDS Failover

```bash
# Reboot RDS with failover (simulates AZ failure)
aws rds reboot-db-instance \
  --db-instance-identifier cloudstack-db \
  --force-failover

# In a separate terminal, keep hitting the health endpoint
watch -n 2 "curl -s http://$ALB_DNS/health | python3 -m json.tool"

# Observe: brief DB error during failover (~60-90 seconds), then recovers automatically
```

### Test B — EC2 Instance Recovery

```bash
# Terminate one instance manually
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names cloudstack-asg \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

aws ec2 terminate-instances --instance-ids $INSTANCE_ID

# Watch ASG automatically launch a replacement
watch -n 10 "aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names cloudstack-asg \
  --query 'AutoScalingGroups[0].Instances[*].{ID:InstanceId,State:LifecycleState}' \
  --output table"
```

### Test C — Deploy a code change

1. Edit `app/templates/index.html` — change any text
2. `git add . && git commit -m "test: update UI" && git push`
3. Watch GitHub Actions → deployment runs with zero downtime

---

## Quick Reference — All Resource IDs

Run this after the full setup to print a summary:

```bash
echo "=== CloudStack Resource Summary ==="
echo "VPC:         $VPC_ID"
echo "IGW:         $IGW_ID"
echo "NAT:         $NAT_ID"
echo "PUB_1A:      $PUB_1A"
echo "PUB_1B:      $PUB_1B"
echo "PRIV_1A:     $PRIV_1A"
echo "PRIV_1B:     $PRIV_1B"
echo "DB_1A:       $DB_1A"
echo "DB_1B:       $DB_1B"
echo "ALB_SG:      $ALB_SG"
echo "APP_SG:      $APP_SG"
echo "RDS_SG:      $RDS_SG"
echo "TG_ARN:      $TG_ARN"
echo "ALB_DNS:     http://$ALB_DNS"
echo "RDS:         $RDS_ENDPOINT"
echo "==================================="
```

---

## Cleanup (when done — to avoid AWS charges)

```bash
# Delete in reverse order of creation
aws autoscaling delete-auto-scaling-group --auto-scaling-group-name cloudstack-asg --force-delete
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
aws elbv2 delete-target-group --target-group-arn $TG_ARN
aws rds delete-db-instance --db-instance-identifier cloudstack-db \
  --skip-final-snapshot --delete-automated-backups
aws ec2 delete-nat-gateway --nat-gateway-id $NAT_ID
# Wait 60s for NAT Gateway to delete, then release EIP
aws ec2 release-address --allocation-id $EIP_ALLOC
aws ec2 delete-vpc --vpc-id $VPC_ID   # deletes subnets, route tables, SGs
aws s3 rb s3://$BUCKET_NAME --force
aws secretsmanager delete-secret --secret-id prod/db/mysql-credentials --force-delete-without-recovery
```
