#!/usr/bin/env bash
#
# Provision the backend tier: security groups, RDS, ECR, S3, IAM, EC2.
#
#   bash infra/aws/01_provision.sh
#
# Console/CLI first, Terraform later (infra/terraform imports what this creates).
# Writing Terraform for infrastructure nobody has stood up yet turns a two-hour
# task into a six-hour one; capturing it afterwards costs an hour and produces
# state that matches reality. That ordering is a deliberate choice -- say so if
# a judge asks.
#
# Idempotent: safe to re-run. Every create is guarded by a lookup.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"        # Mumbai: lowest latency for judges in India
PROJECT="${PROJECT:-renewable}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.large}"  # 8 GB: bge-m3 + reranker need ~3 GB resident
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t4g.micro}"
SUFFIX="${SUFFIX:-$(aws sts get-caller-identity --query Account --output text | tail -c 7)}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" \
    --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"

echo "account=$ACCOUNT_ID region=$REGION vpc=$VPC_ID"

# NOTE ON NETWORK TOPOLOGY
# EC2 goes in a PUBLIC subnet with an ALB in front. That is deliberate: the
# alternative (private subnet) needs a NAT Gateway at roughly Rs 280/day, which
# is the single largest accidental AWS bill in hackathon projects and buys
# nothing here. Security comes from the security-group chain below, not from
# address privacy.

# ----------------------------------------------------------------- security groups
sg_id() {
    aws ec2 describe-security-groups --region "$REGION" \
        --filters "Name=group-name,Values=$1" "Name=vpc-id,Values=$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null
}

ensure_sg() {
    local name="$1" desc="$2" id
    id="$(sg_id "$name")"
    if [[ "$id" == "None" || -z "$id" ]]; then
        id="$(aws ec2 create-security-group --region "$REGION" \
            --group-name "$name" --description "$desc" --vpc-id "$VPC_ID" \
            --query GroupId --output text)"
        echo "created sg $name = $id" >&2
    fi
    echo "$id"
}

ALB_SG="$(ensure_sg "$PROJECT-alb-sg" "ALB: public HTTPS/HTTP")"
EC2_SG="$(ensure_sg "$PROJECT-ec2-sg" "Backend: 8000 from ALB only")"
RDS_SG="$(ensure_sg "$PROJECT-rds-sg" "Postgres: 5432 from backend only")"

allow() {  # allow <sg> <port> <cidr-or-sg>
    local target="$1" port="$2" source="$3"
    if [[ "$source" == sg-* ]]; then
        aws ec2 authorize-security-group-ingress --region "$REGION" \
            --group-id "$target" --protocol tcp --port "$port" \
            --source-group "$source" 2>/dev/null || true
    else
        aws ec2 authorize-security-group-ingress --region "$REGION" \
            --group-id "$target" --protocol tcp --port "$port" \
            --cidr "$source" 2>/dev/null || true
    fi
}

# The whole chain. Note what is NOT here: no 0.0.0.0/0 on 8000, none on 5432,
# and no port 22 anywhere. Shell access is SSM Session Manager, so there is no
# key pair to lose and every session is audited.
allow "$ALB_SG" 443 0.0.0.0/0
allow "$ALB_SG" 80  0.0.0.0/0
allow "$EC2_SG" 8000 "$ALB_SG"
allow "$RDS_SG" 5432 "$EC2_SG"
echo "security group chain: internet -> $ALB_SG -> $EC2_SG -> $RDS_SG"

# ------------------------------------------------------------------------- RDS
DB_ID="$PROJECT-db"
if ! aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$DB_ID" >/dev/null 2>&1; then
    DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/@" ')"
    aws rds create-db-instance --region "$REGION" \
        --db-instance-identifier "$DB_ID" \
        --db-instance-class "$DB_INSTANCE_CLASS" \
        --engine postgres --engine-version 15.7 \
        --master-username renewable \
        --master-user-password "$DB_PASSWORD" \
        --allocated-storage 20 --storage-type gp3 \
        --backup-retention-period 1 --no-multi-az \
        --db-name renewable \
        --no-publicly-accessible \
        --vpc-security-group-ids "$RDS_SG" >/dev/null
    echo "creating $DB_ID (takes ~8 minutes)"

    aws ssm put-parameter --region "$REGION" \
        --name "/$PROJECT/db_password" --value "$DB_PASSWORD" \
        --type SecureString --overwrite >/dev/null
    echo "db password stored at /$PROJECT/db_password -- it is not printed here"
else
    echo "rds $DB_ID already exists"
fi

# ------------------------------------------------------------------- ECR and S3
aws ecr describe-repositories --region "$REGION" --repository-names "$PROJECT-backend" >/dev/null 2>&1 || \
    aws ecr create-repository --region "$REGION" \
        --repository-name "$PROJECT-backend" \
        --image-scanning-configuration scanOnPush=true >/dev/null
echo "ecr: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$PROJECT-backend"

for bucket in "$PROJECT-data-$SUFFIX" "$PROJECT-frontend-$SUFFIX"; do
    if ! aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
        aws s3api create-bucket --bucket "$bucket" --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
        # Both buckets stay private. The frontend is served through CloudFront
        # with Origin Access Control, never as a public website bucket.
        aws s3api put-public-access-block --bucket "$bucket" \
            --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
        echo "created s3://$bucket"
    fi
done

# ------------------------------------------------------------------------- IAM
ROLE="$PROJECT-ec2-role"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' >/dev/null

    # SSM Session Manager: this is what replaces SSH and a key pair.
    aws iam attach-role-policy --role-name "$ROLE" \
        --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
    aws iam attach-role-policy --role-name "$ROLE" \
        --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
    aws iam attach-role-policy --role-name "$ROLE" \
        --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

    # Scoped to this project's parameters and buckets, not "*".
    aws iam put-role-policy --role-name "$ROLE" --policy-name "$PROJECT-app-access" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"ssm:GetParameter\", \"ssm:GetParameters\", \"ssm:GetParametersByPath\"],
                    \"Resource\": \"arn:aws:ssm:$REGION:$ACCOUNT_ID:parameter/$PROJECT/*\"
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": \"kms:Decrypt\",
                    \"Resource\": \"*\",
                    \"Condition\": {\"StringEquals\": {\"kms:ViaService\": \"ssm.$REGION.amazonaws.com\"}}
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"s3:GetObject\", \"s3:PutObject\", \"s3:ListBucket\"],
                    \"Resource\": [
                        \"arn:aws:s3:::$PROJECT-data-$SUFFIX\",
                        \"arn:aws:s3:::$PROJECT-data-$SUFFIX/*\"
                    ]
                }
            ]
        }"

    aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
    aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
    echo "created iam role $ROLE"
    sleep 10   # instance profiles are not immediately usable
fi

# ------------------------------------------------------------------------- EC2
INSTANCE_ID="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$PROJECT-backend" "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null)"

if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    AMI_ID="$(aws ssm get-parameter --region "$REGION" \
        --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
        --query 'Parameter.Value' --output text)"
    SUBNET_ID="$(aws ec2 describe-subnets --region "$REGION" \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
        --query 'Subnets[0].SubnetId' --output text)"

    INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
        --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" \
        --subnet-id "$SUBNET_ID" --security-group-ids "$EC2_SG" \
        --iam-instance-profile "Name=$ROLE" \
        --associate-public-ip-address \
        --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=40,VolumeType=gp3}' \
        --user-data "file://$(dirname "$0")/user_data.sh" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$PROJECT-backend}]" \
        --metadata-options "HttpTokens=required" \
        --query 'Instances[0].InstanceId' --output text)"
    echo "launched $INSTANCE_ID"
else
    echo "ec2 $INSTANCE_ID already running"
fi

# 40 GB root volume, not the 8 GB default: the image alone is ~4.5 GB and Docker
# keeps the previous one around after a deploy.

cat <<SUMMARY

------------------------------------------------------------------
Provisioned. Record these as GitHub repository secrets:

  AWS_ACCOUNT_ID     $ACCOUNT_ID
  ECR_REGISTRY       $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
  EC2_INSTANCE_ID    $INSTANCE_ID

Buckets:
  s3://$PROJECT-data-$SUFFIX
  s3://$PROJECT-frontend-$SUFFIX

Next:
  1. Wait for RDS:  aws rds wait db-instance-available --db-instance-identifier $DB_ID --region $REGION
  2. Enable pgvector FROM THE EC2 BOX (RDS is not publicly reachable):
       aws ssm start-session --target $INSTANCE_ID --region $REGION
       psql -h <rds-endpoint> -U renewable -d renewable -c 'CREATE EXTENSION IF NOT EXISTS vector;'
  3. Apply migrations, then build the index (colab_notebooks/10_rag_embed.ipynb)
  4. bash infra/aws/02_cloudfront.sh
  5. bash infra/aws/03_observability.sh

Verify no security group is open to the world on a data port:
  aws ec2 describe-security-groups --region $REGION --group-ids $EC2_SG $RDS_SG \\
    --query 'SecurityGroups[].IpPermissions[?contains(to_string(IpRanges), \`0.0.0.0/0\`)]'
  (expected: two empty lists)
------------------------------------------------------------------
SUMMARY
