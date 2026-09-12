#!/usr/bin/env bash
#
# The nightly pipeline trigger and the four alarms worth having.
#
#   bash infra/aws/03_observability.sh
#
# Alarms are deliberately few. An alarm nobody acts on is noise, and noise is how
# the one alarm that mattered gets ignored.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-renewable}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ALERT_EMAIL="${ALERT_EMAIL:-}"

# ------------------------------------------------------------------- SNS topic
TOPIC_ARN="$(aws sns create-topic --region "$REGION" --name "$PROJECT-alerts" \
    --query TopicArn --output text)"
if [[ -n "$ALERT_EMAIL" ]]; then
    aws sns subscribe --region "$REGION" --topic-arn "$TOPIC_ARN" \
        --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
    echo "subscription sent to $ALERT_EMAIL -- confirm it from your inbox"
fi

# ---------------------------------------------------------------- log group
aws logs create-log-group --region "$REGION" --log-group-name "/$PROJECT/backend" 2>/dev/null || true
aws logs put-retention-policy --region "$REGION" \
    --log-group-name "/$PROJECT/backend" --retention-in-days 7

# The copilot logs the literal token `llm_fail` on every provider failure
# (backend/modules/rag/llm.py). This filter turns that into a metric.
aws logs put-metric-filter --region "$REGION" \
    --log-group-name "/$PROJECT/backend" \
    --filter-name llm-failures \
    --filter-pattern '"llm_fail"' \
    --metric-transformations \
        "metricName=LLMFailures,metricNamespace=$PROJECT,metricValue=1,defaultValue=0"

# Same idea for the guardrail: how often the copilot tried to state a number the
# engine did not produce. Not an alarm -- a number to be able to quote.
aws logs put-metric-filter --region "$REGION" \
    --log-group-name "/$PROJECT/backend" \
    --filter-name guardrail-strips \
    --filter-pattern '"guardrail stripped"' \
    --metric-transformations \
        "metricName=GuardrailStrips,metricNamespace=$PROJECT,metricValue=1,defaultValue=0"

# ----------------------------------------------------------------------- alarms
alarm() {  # alarm <name> <description> <namespace> <metric> <threshold> <periods> [extra...]
    local name="$1" desc="$2" ns="$3" metric="$4" threshold="$5" periods="$6"; shift 6
    aws cloudwatch put-metric-alarm --region "$REGION" \
        --alarm-name "$PROJECT-$name" \
        --alarm-description "$desc" \
        --namespace "$ns" --metric-name "$metric" \
        --statistic Sum --period 300 --evaluation-periods "$periods" \
        --threshold "$threshold" --comparison-operator GreaterThanThreshold \
        --treat-missing-data notBreaching \
        --alarm-actions "$TOPIC_ARN" "$@"
    echo "  alarm: $PROJECT-$name"
}

# Both providers down means the copilot is serving fallback templates. The demo
# still works, but the cited-answer segment does not.
alarm llm-all-failed "Both LLM providers failing" "$PROJECT" LLMFailures 5 1

ALB_ARN_SUFFIX="$(aws elbv2 describe-load-balancers --region "$REGION" --names "$PROJECT-alb" \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null | \
    sed 's|.*loadbalancer/||' || echo "")"

if [[ -n "$ALB_ARN_SUFFIX" && "$ALB_ARN_SUFFIX" != "None" ]]; then
    # The backend is down during judging. Nothing else matters more than this.
    alarm backend-5xx "Backend returning 5xx" AWS/ApplicationELB HTTPCode_Target_5XX_Count 5 1 \
        --dimensions "Name=LoadBalancer,Value=$ALB_ARN_SUFFIX"
fi

# Tomorrow's dashboard would be empty. Emitted by the pipeline itself.
alarm pipeline-failed "Nightly pipeline failed" "$PROJECT" PipelineFailed 0 1

INSTANCE_ID="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$PROJECT-backend" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null)"

if [[ -n "$INSTANCE_ID" && "$INSTANCE_ID" != "None" ]]; then
    # bge-m3 + reranker + two uvicorn workers on 8 GB. The OOM killer taking the
    # container mid-demo looks like a crash with no stack trace.
    aws cloudwatch put-metric-alarm --region "$REGION" \
        --alarm-name "$PROJECT-ec2-memory-high" \
        --alarm-description "Backend memory above 85%" \
        --namespace CWAgent --metric-name mem_used_percent \
        --statistic Average --period 300 --evaluation-periods 2 \
        --threshold 85 --comparison-operator GreaterThanThreshold \
        --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
        --treat-missing-data notBreaching \
        --alarm-actions "$TOPIC_ARN"
    echo "  alarm: $PROJECT-ec2-memory-high (needs the CloudWatch agent installed)"
fi

# ------------------------------------------------------- EventBridge daily run
# 02:30 UTC = 08:00 IST, ahead of the RLDC schedule-submission cutoff.
SCHEDULER_ROLE="$PROJECT-scheduler-role"
if ! aws iam get-role --role-name "$SCHEDULER_ROLE" >/dev/null 2>&1; then
    aws iam create-role --role-name "$SCHEDULER_ROLE" --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "scheduler.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' >/dev/null
    aws iam put-role-policy --role-name "$SCHEDULER_ROLE" --policy-name invoke-pipeline \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Action\": \"lambda:InvokeFunction\",
                \"Resource\": \"arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$PROJECT-trigger-pipeline\"
            }]
        }"
    sleep 10
fi

aws scheduler create-schedule --region "$REGION" \
    --name "$PROJECT-daily-pipeline" \
    --schedule-expression "cron(30 2 * * ? *)" \
    --schedule-expression-timezone "UTC" \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "{
        \"Arn\": \"arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$PROJECT-trigger-pipeline\",
        \"RoleArn\": \"arn:aws:iam::$ACCOUNT_ID:role/$SCHEDULER_ROLE\",
        \"RetryPolicy\": {\"MaximumRetryAttempts\": 2}
    }" 2>/dev/null || echo "  schedule already exists"

cat <<NOTE

------------------------------------------------------------------
EventBridge fires $PROJECT-trigger-pipeline at 02:30 UTC (08:00 IST).

The Lambda (infra/aws/lambda_trigger_pipeline.py) reads the API key from
SSM at invocation time. The key is deliberately NOT in the schedule's
target payload: target definitions are readable by anyone with console
access to EventBridge.

Coordinate with Member 2: POST /pipeline/run must return 202 with a
run_id immediately and do the work in a background task. A scheduler
target that waits four minutes for a synchronous pipeline times out, and
then retries, and then you have two pipelines running.

Verify the trigger fired at least once unattended before demo day:
  aws logs tail /aws/lambda/$PROJECT-trigger-pipeline --since 24h --region $REGION
  psql ... -c 'SELECT id, run_time, status FROM job_runs ORDER BY run_time DESC LIMIT 5;'
------------------------------------------------------------------
NOTE
