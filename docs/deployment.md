# Deployment

**Owner:** Member 4. Everything here is reproducible from a clean AWS account.

> **See also:** `docs/runbook.md` — demo-day failover, failure modes, and alarm handling.

## Table of Contents

- [The fallback ladder](#the-fallback-ladder)
- [Rung 1 — local](#rung-1--local)
- [Building the regulation index](#building-the-regulation-index)
- [Rungs 3–6 — AWS](#rungs-36--aws)
- [CI/CD](#cicd)
- [Cost control](#cost-control)
- [Terraform](#terraform)


## The fallback ladder

Climb as far as time allows. **Every rung is a working demo.** Do not start rung 3 until
rung 2 is committed and green.

| Rung | What | When | Cost if the next rung fails |
|---|---|---|---|
| 1 | `docker compose up` on a laptop, seeded DB | Day 1 | Nothing. This path always works. |
| 2 | + Cloudflare Tunnel / ngrok on :8000 | 10 min | Public URL, zero AWS |
| 3 | + EC2 running compose, public IP | Day 9 | Real cloud, no CDN |
| 4 | + CloudFront + S3 + ALB | Day 10 | **The demo URL** |
| 5 | + GitHub Actions CI/CD | Day 11–12 | "We ship on merge" |
| 6 | + EventBridge, CloudWatch, Terraform | Day 13 | The production story |

If AWS credits have not landed by Day 9, stop at rung 2 and spend the saved days making the
copilot demonstrably better. A polished copilot on a tunnel beats a half-configured VPC every
time.

**Rung 1 is never retired.** Keep the laptop stack running through the entire judging session.
Venue wifi fails; know which URL to switch to within fifteen seconds.

---

## Rung 1 — local

```bash
cp .env.example .env
docker compose up            # add --profile dev for the Vite frontend
```

Verify:

```bash
curl localhost:8000/health
curl localhost:8000/rag/health
docker compose exec db psql -U renewable -d renewable -c '\dx'   # expect: vector, pg_trgm
```

`init_db.sql` runs **only** when the `pgdata` volume is first created. If it changes after
someone has already started the stack, they need `docker compose down -v`.

To run the real copilot locally, set `RAG_COPILOT_TYPE=production` and a `GROQ_API_KEY` in
`.env`, install `requirements-ml.txt`, and build the index (below).

---

## Building the regulation index

Required before the copilot can cite anything. Offline, never in a request path.

```bash
python scripts/hash_regulations.py          # pin the PDF revisions
python scripts/build_index.py --dry-run     # validate the chunker FIRST
python scripts/build_index.py --truncate    # embed and write
python scripts/eval_retrieval.py --verbose  # recall@5 must be >= 0.7
```

On a GPU use `colab_notebooks/10_rag_embed.ipynb` — under a minute on a T4 versus 10–20 on a
laptop CPU.

Colab cannot reach a private RDS. Tunnel first:

```bash
aws ssm start-session --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5432"]}'
```

Do **not** make RDS publicly accessible to save time.

---

## Rungs 3–6 — AWS

Run in order. Every script is idempotent.

```bash
export AWS_REGION=ap-south-1        # Mumbai: lowest latency for judges in India

bash infra/aws/00_secrets.sh        # SSM parameters (prompts, never arguments)
bash infra/aws/01_provision.sh      # SGs, RDS, ECR, S3, IAM, EC2
bash infra/aws/02_cloudfront.sh     # ALB + CloudFront -> the demo URL
bash infra/aws/03_observability.sh  # EventBridge schedule + 4 alarms
```

After `01_provision.sh`:

```bash
aws rds wait db-instance-available --db-instance-identifier renewable-db

# pgvector must be enabled from inside the VPC -- RDS is not publicly reachable.
aws ssm start-session --target <instance-id>
psql -h <rds-endpoint> -U renewable -d renewable -c 'CREATE EXTENSION IF NOT EXISTS vector;'
alembic upgrade head
```

### Network shape

```
Users (HTTPS)
   |
CloudFront  (default *.cloudfront.net certificate -- no domain, no Route 53, no ACM)
   |-- /*      -> S3 (private bucket + Origin Access Control)
   +-- /api/*  -> ALB (HTTP inside AWS) -> EC2:8000 -> RDS:5432
```

Security-group chain, and nothing else:

| Group | Ingress | From |
|---|---|---|
| ALB | 443, 80 | `0.0.0.0/0` |
| Backend | 8000 | ALB security group **only** |
| RDS | 5432 | Backend security group **only** |
| SSH | — | none. SSM Session Manager, so there is no key pair to lose |

**No NAT Gateway.** The backend is in a public subnet behind the ALB. A NAT Gateway is about
Rs 280/day and is the single largest accidental bill in hackathon AWS; it buys nothing here,
because the protection comes from the rules above rather than from an unroutable address.

Verify before demo day:

```bash
aws ec2 describe-security-groups --group-ids <ec2-sg> <rds-sg> \
  --query 'SecurityGroups[].IpPermissions[?contains(to_string(IpRanges), `0.0.0.0/0`)]'
# expected: two empty lists
```

---

## CI/CD

### GitHub repository secrets

| Secret | From |
|---|---|
| `AWS_ACCOUNT_ID` | `01_provision.sh` summary |
| `ECR_REGISTRY` | `01_provision.sh` summary |
| `EC2_INSTANCE_ID` | `01_provision.sh` summary |
| `CF_DISTRIBUTION_ID` | `02_cloudfront.sh` summary |

No AWS access keys. Authentication is OIDC.

### One-time OIDC setup

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

Trust policy for `GitHubActionsDeployRole`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<ACCOUNT>:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike":   { "token.actions.githubusercontent.com:sub": "repo:<ORG>/<REPO>:ref:refs/heads/main" }
    }
  }]
}
```

> **The `StringLike` condition on `sub` is not optional.** Without it, *any* GitHub repository
> on the internet can assume this role. It is the most copy-pasted security hole in Actions
> setups. Worth mentioning in the demo — judges notice.

The role needs: ECR push, `ssm:SendCommand` on the instance, and
`cloudfront:CreateInvalidation`.

### What runs when

| Trigger | Workflow | Does |
|---|---|---|
| push to any branch | `ci` → `test` | ruff + pytest, ~2 min |
| push to main / PR to main | `ci` → `image` | docker build + trivy, push to ECR on main |
| `ci` succeeds on main | `deploy` | SSM roll + health check + CloudFront invalidation |
| manual | `deploy` (`workflow_dispatch`) | rollback / redeploy |

### Frontend

```bash
cd frontend && npm run build
bash infra/aws/deploy_frontend.sh
```

Two settings that break the demo if missed, both handled by the scripts — check them if
something looks wrong:

1. **CORS.** The CloudFront domain must be in `CORS_ORIGINS` in SSM, and the backend restarted.
   Symptom: the dashboard loads and every panel spins forever, with CORS errors in the console.
2. **SPA routing.** CloudFront maps 403/404 → `/index.html` with status 200. Symptom: the
   dashboard works but a refresh on `/plant/GJ_SOLAR_A` returns AccessDenied.

---

## Cost control

| Resource | ~Rs/day | Action after judging |
|---|---|---|
| EC2 t3.large | 170 | `aws ec2 stop-instances` immediately |
| RDS db.t4g.micro | 60 | snapshot, then delete |
| CloudFront + S3 | <10 | leave up — it is the portfolio link |
| NAT Gateway | 280 | **never provisioned** |

```bash
# After judging
aws ec2 stop-instances --instance-ids <id>
aws rds create-db-snapshot --db-instance-identifier renewable-db \
    --db-snapshot-identifier renewable-final
aws rds delete-db-instance --db-instance-identifier renewable-db --skip-final-snapshot
```

---

## Terraform

Written last and imported, not applied. See [`infra/terraform/README.md`](../infra/terraform/README.md).

`terraform plan` reporting **no changes** against live infrastructure is the proof that the
code matches reality. State goes to S3 with DynamoDB locking, never to git — it contains the
RDS password in plaintext.
