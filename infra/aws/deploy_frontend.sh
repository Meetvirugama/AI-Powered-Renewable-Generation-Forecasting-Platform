#!/usr/bin/env bash
#
# Publish Member 3's build to S3 and invalidate the CDN.
#
#   bash infra/aws/deploy_frontend.sh [path-to-dist]
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-renewable}"
SUFFIX="${SUFFIX:-$(aws sts get-caller-identity --query Account --output text | tail -c 7)}"
BUCKET="$PROJECT-frontend-$SUFFIX"
DIST="${1:-frontend/dist}"

[[ -d "$DIST" ]] || { echo "no build at $DIST -- run 'npm run build' in frontend/ first"; exit 1; }
[[ -f "$DIST/index.html" ]] || { echo "$DIST has no index.html"; exit 1; }

# Hashed assets get a long cache; index.html must not, or a deploy ships new
# assets that the old cached HTML never references.
aws s3 sync "$DIST" "s3://$BUCKET/" --delete --region "$REGION" \
    --exclude "index.html" \
    --cache-control "public,max-age=31536000,immutable"

aws s3 cp "$DIST/index.html" "s3://$BUCKET/index.html" --region "$REGION" \
    --cache-control "no-cache,no-store,must-revalidate" \
    --content-type "text/html"

DIST_ID="$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='$PROJECT dashboard'].Id" --output text)"

INVALIDATION="$(aws cloudfront create-invalidation --distribution-id "$DIST_ID" \
    --paths "/*" --query 'Invalidation.Id' --output text)"

DOMAIN="$(aws cloudfront get-distribution --id "$DIST_ID" \
    --query 'Distribution.DomainName' --output text)"

echo "deployed to https://$DOMAIN (invalidation $INVALIDATION, ~60s to propagate)"
