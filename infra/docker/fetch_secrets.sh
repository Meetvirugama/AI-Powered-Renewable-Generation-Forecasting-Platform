#!/usr/bin/env bash
#
# Render /opt/renewable/.env from SSM Parameter Store, on the EC2 host, at boot
# and before every deploy.
#
# Secrets are read at container start rather than baked into the image: an image
# layer containing an API key is readable by anyone who can pull from ECR, and it
# survives key rotation.
#
# Parameter naming: /renewable/groq_api_key -> GROQ_API_KEY
set -euo pipefail

PREFIX="${SSM_PREFIX:-/renewable}"
TARGET="${ENV_FILE:-/opt/renewable/.env}"
REGION="${AWS_REGION:-ap-south-1}"

umask 077
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

aws ssm get-parameters-by-path \
    --path "$PREFIX" \
    --with-decryption \
    --region "$REGION" \
    --query 'Parameters[].[Name,Value]' \
    --output text \
| while IFS=$'\t' read -r name value; do
    key="$(basename "$name" | tr '[:lower:]' '[:upper:]')"
    # Quote the value: API keys can contain characters the shell would otherwise
    # interpret when docker compose sources this file.
    printf '%s=%s\n' "$key" "$value"
done > "$TMP"

if [[ ! -s "$TMP" ]]; then
    echo "fetch_secrets: no parameters found under $PREFIX in $REGION" >&2
    exit 1
fi

install -m 600 "$TMP" "$TARGET"
echo "fetch_secrets: wrote $(wc -l < "$TARGET") parameters to $TARGET"
