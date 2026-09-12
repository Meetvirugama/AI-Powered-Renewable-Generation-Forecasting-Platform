#!/usr/bin/env bash
#
# Import the infrastructure that infra/aws/*.sh already created.
#
#   cd infra/terraform && terraform init && bash import.sh && terraform plan
#
# `terraform plan` must report "No changes" afterwards. Anything else means this
# code and the live infrastructure disagree -- fix the code, do not apply.
#
# Imports are ordered by dependency. Each is skipped if already in state, so this
# is safe to re-run after fixing one failure.
set -uo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-renewable}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

lookup_sg() {
    aws ec2 describe-security-groups --region "$REGION" \
        --filters "Name=group-name,Values=$1" \
        --query 'SecurityGroups[0].GroupId' --output text
}

INSTANCE_ID="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$PROJECT-backend" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text)"
ALB_ARN="$(aws elbv2 describe-load-balancers --region "$REGION" --names "$PROJECT-alb" \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
TG_ARN="$(aws elbv2 describe-target-groups --region "$REGION" --names "$PROJECT-tg" \
    --query 'TargetGroups[0].TargetGroupArn' --output text)"
LISTENER_ARN="$(aws elbv2 describe-listeners --region "$REGION" \
    --load-balancer-arn "$ALB_ARN" --query 'Listeners[0].ListenerArn' --output text)"
SUFFIX="${SUFFIX:-$(echo "$ACCOUNT_ID" | tail -c 7)}"

imp() {  # imp <address> <id>
    if terraform state show "$1" >/dev/null 2>&1; then
        echo "  already in state: $1"
        return 0
    fi
    echo "importing $1 <- $2"
    terraform import -var "bucket_suffix=$SUFFIX" "$1" "$2" || echo "  FAILED: $1"
}

imp aws_security_group.alb                "$(lookup_sg "$PROJECT-alb-sg")"
imp aws_security_group.backend            "$(lookup_sg "$PROJECT-ec2-sg")"
imp aws_security_group.database           "$(lookup_sg "$PROJECT-rds-sg")"

imp aws_db_instance.main                  "$PROJECT-db"
imp aws_ecr_repository.backend            "$PROJECT-backend"
imp aws_ecr_lifecycle_policy.backend      "$PROJECT-backend"

imp aws_s3_bucket.data                    "$PROJECT-data-$SUFFIX"
imp aws_s3_bucket.frontend                "$PROJECT-frontend-$SUFFIX"
imp aws_s3_bucket_public_access_block.data     "$PROJECT-data-$SUFFIX"
imp aws_s3_bucket_public_access_block.frontend "$PROJECT-frontend-$SUFFIX"

imp aws_iam_role.backend                  "$PROJECT-ec2-role"
imp aws_iam_instance_profile.backend      "$PROJECT-ec2-role"
imp aws_iam_role_policy.app_access        "$PROJECT-ec2-role:$PROJECT-app-access"
imp aws_iam_role_policy_attachment.ssm    "$PROJECT-ec2-role/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
imp aws_iam_role_policy_attachment.ecr    "$PROJECT-ec2-role/arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"

imp aws_instance.backend                  "$INSTANCE_ID"
imp aws_lb.backend                        "$ALB_ARN"
imp aws_lb_target_group.backend           "$TG_ARN"
imp aws_lb_listener.http                  "$LISTENER_ARN"
imp aws_lb_target_group_attachment.backend "$TG_ARN/$INSTANCE_ID/8000"

imp aws_cloudwatch_log_group.backend      "/$PROJECT/backend"

cat <<'NOTE'

Now run:

    terraform plan -var "bucket_suffix=<suffix>"

"No changes" is the goal and the proof. If plan wants to destroy and recreate
something, the code is wrong -- adjust the resource block to match reality
rather than letting apply rebuild live infrastructure mid-sprint.
NOTE
