#!/usr/bin/env bash
#
# Seed SSM Parameter Store with the application's secrets.
#
#   bash infra/aws/00_secrets.sh
#
# Run this FIRST. The EC2 instance renders its .env from these parameters at
# every boot and every deploy (infra/docker/fetch_secrets.sh), so a missing
# parameter surfaces as a container that starts and then cannot reach anything.
#
# Values are prompted for, never passed as arguments: an argument lands in shell
# history, in `ps` output, and in CloudTrail's request log.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PREFIX="${SSM_PREFIX:-/renewable}"

# Parameter name -> prompt. The name maps to an env var by uppercasing:
#   /renewable/groq_api_key -> GROQ_API_KEY
declare -a PARAMS=(
    "groq_api_key:Groq API key (console.groq.com)"
    "gemini_api_key:Gemini API key (aistudio.google.com)"
    "database_url:Full DATABASE_URL for RDS (postgresql+psycopg2://...)"
    "pipeline_api_key:Shared secret for POST /pipeline/run"
    "cors_origins:Comma-separated allowed origins, including the CloudFront domain"
)

echo "Writing SecureString parameters under $PREFIX in $REGION"
echo

for entry in "${PARAMS[@]}"; do
    name="${entry%%:*}"
    prompt="${entry#*:}"

    if aws ssm get-parameter --name "$PREFIX/$name" --region "$REGION" >/dev/null 2>&1; then
        read -r -p "$name already exists. Overwrite? [y/N] " reply
        [[ "$reply" =~ ^[Yy]$ ]] || { echo "  skipped $name"; continue; }
    fi

    read -r -s -p "$prompt: " value
    echo
    [[ -n "$value" ]] || { echo "  empty, skipped $name"; continue; }

    aws ssm put-parameter \
        --name "$PREFIX/$name" \
        --value "$value" \
        --type SecureString \
        --overwrite \
        --region "$REGION" >/dev/null
    echo "  wrote $PREFIX/$name"
done

echo
echo "Stored parameters:"
aws ssm get-parameters-by-path --path "$PREFIX" --region "$REGION" \
    --query 'Parameters[].Name' --output table

cat <<'NOTE'

The EC2 instance profile needs ssm:GetParameter, ssm:GetParameters and
ssm:GetParametersByPath on this path, plus kms:Decrypt on the key that encrypts
them (alias/aws/ssm by default). 01_provision.sh attaches that policy.

The pipeline API key is deliberately NOT put in the EventBridge target payload:
target definitions are readable by anyone with console access. The Lambda reads
it from here at invocation time instead.
NOTE
