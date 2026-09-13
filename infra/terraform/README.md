# Terraform — captured, not authored first

This directory describes infrastructure that **already exists**, created by the scripts in
`infra/aws/`. It is imported, not applied from scratch.

> The live deployment runs on Azure ([docs/deployment_azure.md](../../docs/deployment_azure.md)).
> This Terraform captures the alternative AWS path described in
> [docs/deployment.md](../../docs/deployment.md).

That ordering is deliberate. Writing Terraform for infrastructure nobody has stood up yet
means debugging your HCL and your architecture at the same time, and it reliably turns a
two-hour task into a six-hour one. Standing it up with the CLI first and capturing it
afterwards costs about an hour and produces state that provably matches reality. If a judge
asks why the Terraform came last, that is the answer — and `terraform plan` reporting **no
changes** against live infrastructure is the evidence.

## Layout

```
main.tf        resources, one block per thing infra/aws/ creates
variables.tf   region, project name, instance sizes
outputs.tf     the values other people need (demo URL, instance id, ECR registry)
versions.tf    provider pinning + remote state backend
import.sh      the import commands, in dependency order
```

## Capturing existing infrastructure

```bash
cd infra/terraform
terraform init

# Fill in the ids from the summary that 01_provision.sh printed, then:
bash import.sh

# The test that matters. Anything other than "No changes" means the code and
# the live infrastructure disagree -- fix the code, do not apply.
terraform plan
```

Commit only after `terraform plan` is clean.

## State

State goes in S3 with DynamoDB locking, never in git:

```bash
aws s3 mb s3://renewable-tfstate-<suffix>
aws s3api put-bucket-versioning --bucket renewable-tfstate-<suffix> \
    --versioning-configuration Status=Enabled
aws dynamodb create-table --table-name renewable-tflock \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST
```

Then uncomment the `backend "s3"` block in `versions.tf` and re-run `terraform init`.

**`*.tfstate*` is in `.gitignore` and must stay there.** State contains the RDS master
password in plaintext. A state file in git history is a credential leak that survives every
later fix.

## What is not captured here

The CloudFront distribution and the OAC are left to `infra/aws/02_cloudfront.sh`. Importing a
distribution mid-sprint risks a `terraform apply` recreating it, which changes the demo URL —
and that URL is in Member 3's `.env.production` and in everyone's browser history. The cost of
managing it by script is lower than the cost of losing it.
