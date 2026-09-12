#!/usr/bin/env bash
#
# One HTTPS URL for the whole demo: CloudFront in front of an S3 frontend and an
# ALB backend.
#
#   bash infra/aws/02_cloudfront.sh
#
#   Users (HTTPS)
#      |
#   CloudFront  (default *.cloudfront.net certificate)
#      |-- /*      -> S3 origin (React build, private bucket + OAC)
#      +-- /api/*  -> ALB origin (HTTP inside AWS) -> EC2:8000
#
# The shortcut worth knowing: use CloudFront's default *.cloudfront.net
# certificate. Viewers get real HTTPS, CloudFront talks to the ALB over HTTP
# inside AWS, and there is no domain to buy, no Route 53 zone and no ACM DNS
# validation. Buying and validating a domain mid-sprint is a reliable way to lose
# an afternoon to DNS propagation.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-renewable}"
SUFFIX="${SUFFIX:-$(aws sts get-caller-identity --query Account --output text | tail -c 7)}"
BUCKET="$PROJECT-frontend-$SUFFIX"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text)"
SUBNETS="$(aws ec2 describe-subnets --region "$REGION" --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[].SubnetId' --output text)"
ALB_SG="$(aws ec2 describe-security-groups --region "$REGION" \
    --filters "Name=group-name,Values=$PROJECT-alb-sg" --query 'SecurityGroups[0].GroupId' --output text)"
INSTANCE_ID="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$PROJECT-backend" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text)"

# --------------------------------------------------------------------------- ALB
ALB_ARN="$(aws elbv2 describe-load-balancers --region "$REGION" --names "$PROJECT-alb" \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || echo "")"

if [[ -z "$ALB_ARN" || "$ALB_ARN" == "None" ]]; then
    # shellcheck disable=SC2086
    ALB_ARN="$(aws elbv2 create-load-balancer --region "$REGION" \
        --name "$PROJECT-alb" --type application --scheme internet-facing \
        --security-groups "$ALB_SG" --subnets $SUBNETS \
        --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
    echo "created alb"
fi

TG_ARN="$(aws elbv2 describe-target-groups --region "$REGION" --names "$PROJECT-tg" \
    --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || echo "")"

if [[ -z "$TG_ARN" || "$TG_ARN" == "None" ]]; then
    TG_ARN="$(aws elbv2 create-target-group --region "$REGION" \
        --name "$PROJECT-tg" --protocol HTTP --port 8000 --vpc-id "$VPC_ID" \
        --target-type instance \
        --health-check-path /health \
        --health-check-interval-seconds 30 \
        --health-check-timeout-seconds 10 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 5 \
        --query 'TargetGroups[0].TargetGroupArn' --output text)"
    # unhealthy-threshold 5 x 30s: the container needs ~90 s to load bge-m3 after
    # a deploy. A tighter threshold deregisters a healthy-but-loading target and
    # the rollout never converges.
    aws elbv2 register-targets --region "$REGION" \
        --target-group-arn "$TG_ARN" --targets "Id=$INSTANCE_ID"
    aws elbv2 create-listener --region "$REGION" \
        --load-balancer-arn "$ALB_ARN" --protocol HTTP --port 80 \
        --default-actions "Type=forward,TargetGroupArn=$TG_ARN" >/dev/null
    echo "created target group and listener"
fi

ALB_DNS="$(aws elbv2 describe-load-balancers --region "$REGION" \
    --load-balancer-arns "$ALB_ARN" --query 'LoadBalancers[0].DNSName' --output text)"
echo "alb: $ALB_DNS"

# --------------------------------------------------------- CloudFront + S3 (OAC)
OAC_ID="$(aws cloudfront list-origin-access-controls \
    --query "OriginAccessControlList.Items[?Name=='$PROJECT-oac'].Id" --output text 2>/dev/null || echo "")"

if [[ -z "$OAC_ID" ]]; then
    OAC_ID="$(aws cloudfront create-origin-access-control --origin-access-control-config "{
        \"Name\": \"$PROJECT-oac\",
        \"Description\": \"OAC for $BUCKET\",
        \"SigningProtocol\": \"sigv4\",
        \"SigningBehavior\": \"always\",
        \"OriginAccessControlOriginType\": \"s3\"
    }" --query 'OriginAccessControl.Id' --output text)"
    echo "created origin access control"
fi

CONFIG="$(mktemp)"
trap 'rm -f "$CONFIG"' EXIT

cat > "$CONFIG" <<JSON
{
  "CallerReference": "$PROJECT-$(date +%s)",
  "Comment": "$PROJECT dashboard",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "Origins": {
    "Quantity": 2,
    "Items": [
      {
        "Id": "s3-frontend",
        "DomainName": "$BUCKET.s3.$REGION.amazonaws.com",
        "OriginAccessControlId": "$OAC_ID",
        "S3OriginConfig": { "OriginAccessIdentity": "" }
      },
      {
        "Id": "alb-backend",
        "DomainName": "$ALB_DNS",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "http-only",
          "OriginReadTimeout": 60
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-frontend",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] },
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true
  },
  "CacheBehaviors": {
    "Quantity": 1,
    "Items": [
      {
        "PathPattern": "/api/*",
        "TargetOriginId": "alb-backend",
        "ViewerProtocolPolicy": "https-only",
        "AllowedMethods": {
          "Quantity": 7,
          "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
          "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
        },
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3"
      }
    ]
  },
  "CustomErrorResponses": {
    "Quantity": 2,
    "Items": [
      {
        "ErrorCode": 403,
        "ResponsePagePath": "/index.html",
        "ResponseCode": "200",
        "ErrorCachingMinTTL": 10
      },
      {
        "ErrorCode": 404,
        "ResponsePagePath": "/index.html",
        "ResponseCode": "200",
        "ErrorCachingMinTTL": 10
      }
    ]
  },
  "PriceClass": "PriceClass_100"
}
JSON

# The 403/404 -> /index.html mapping above is SPA routing. Without it the
# dashboard loads but a refresh on /plant/GJ_SOLAR_A returns AccessDenied, which
# is exactly the thing a judge does.
# The /api/* behaviour uses the managed CachingDisabled policy and the
# AllViewerExceptHostHeader origin request policy -- caching a POST /rag/query
# response at the CDN would serve one plant's answer to another plant's page.

DIST_ID="$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='$PROJECT dashboard'].Id" --output text 2>/dev/null || echo "")"

if [[ -z "$DIST_ID" ]]; then
    DIST_ID="$(aws cloudfront create-distribution --distribution-config "file://$CONFIG" \
        --query 'Distribution.Id' --output text)"
    echo "created distribution $DIST_ID (15-20 minutes to deploy)"
fi

DIST_DOMAIN="$(aws cloudfront get-distribution --id "$DIST_ID" \
    --query 'Distribution.DomainName' --output text)"

# Let CloudFront read the private bucket, and only this distribution.
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
        \"Effect\": \"Allow\",
        \"Principal\": {\"Service\": \"cloudfront.amazonaws.com\"},
        \"Action\": \"s3:GetObject\",
        \"Resource\": \"arn:aws:s3:::$BUCKET/*\",
        \"Condition\": {
            \"StringEquals\": {
                \"AWS:SourceArn\": \"arn:aws:cloudfront::$ACCOUNT_ID:distribution/$DIST_ID\"
            }
        }
    }]
}"

cat <<SUMMARY

------------------------------------------------------------------
THE DEMO URL:  https://$DIST_DOMAIN

GitHub secret to record:
  CF_DISTRIBUTION_ID   $DIST_ID

Two things that break the demo if they are missed:

1. CORS. Add https://$DIST_DOMAIN to CORS_ORIGINS in SSM and restart the
   backend, or every dashboard panel spins forever with a console CORS error:

     aws ssm put-parameter --name /$PROJECT/cors_origins --type SecureString \\
       --value "https://$DIST_DOMAIN" --overwrite --region $REGION

2. Member 3 needs this URL for frontend/.env.production. Send it now, not
   on demo day.

Deploy the frontend with:  bash infra/aws/deploy_frontend.sh
------------------------------------------------------------------
SUMMARY
