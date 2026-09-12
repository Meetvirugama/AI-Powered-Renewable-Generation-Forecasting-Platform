"""EventBridge target: kick off the nightly pipeline.

Deployed as the Lambda `renewable-trigger-pipeline`, invoked at 02:30 UTC
(08:00 IST) by the schedule in 03_observability.sh.

Deliberately tiny. It holds no business logic -- it makes one authenticated
call and reports what came back. The pipeline itself belongs to Member 2.

The API key is read from SSM at invocation time rather than passed in the
schedule's target payload, because target definitions are readable by anyone
with console access to EventBridge.

Environment:
    BACKEND_URL   http://<alb-dns>            (inside the VPC, no CDN in the path)
    SSM_PREFIX    /renewable
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import boto3

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
SSM_PREFIX = os.getenv("SSM_PREFIX", "/renewable")
TIMEOUT_S = 20

_ssm = boto3.client("ssm")
_cloudwatch = boto3.client("cloudwatch")


def _api_key() -> str:
    return _ssm.get_parameter(
        Name=f"{SSM_PREFIX}/pipeline_api_key", WithDecryption=True
    )["Parameter"]["Value"]


def _emit(failed: int) -> None:
    """Feed the renewable-pipeline-failed alarm."""
    _cloudwatch.put_metric_data(
        Namespace="renewable",
        MetricData=[{"MetricName": "PipelineFailed", "Value": failed, "Unit": "Count"}],
    )


def handler(event, context):  # noqa: ARG001
    request = urllib.request.Request(
        f"{BACKEND_URL}/pipeline/run",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json", "X-API-Key": _api_key()},
    )

    try:
        # The endpoint returns 202 with a run_id and does the work in the
        # background. A 20 s timeout is generous for that; it would be far too
        # short if the pipeline ever became synchronous, which is why the
        # contract says 202.
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = response.read().decode()
            print(f"pipeline triggered: {response.status} {body}")
            _emit(0)
            return {"status": response.status, "body": json.loads(body or "{}")}

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        print(f"pipeline trigger failed: {exc.code} {detail}")
        _emit(1)
        raise

    except Exception as exc:
        # Includes the timeout case. Alarm first, then fail the invocation so
        # the scheduler's retry policy gets its turn.
        print(f"pipeline trigger error: {type(exc).__name__}: {exc}")
        _emit(1)
        raise
