output "demo_url" {
  description = "The single HTTPS URL for the dashboard. Managed by infra/aws/02_cloudfront.sh."
  value       = "see: aws cloudfront list-distributions --query \"DistributionList.Items[?Comment=='${var.project} dashboard'].DomainName\""
}

output "alb_dns_name" {
  description = "CloudFront's backend origin."
  value       = aws_lb.backend.dns_name
}

output "ec2_instance_id" {
  description = "GitHub secret EC2_INSTANCE_ID; also the SSM Session Manager target."
  value       = aws_instance.backend.id
}

output "ecr_registry" {
  description = "GitHub secret ECR_REGISTRY."
  value       = split("/", aws_ecr_repository.backend.repository_url)[0]
}

output "rds_endpoint" {
  description = "Reachable only from the backend security group."
  value       = aws_db_instance.main.address
}

output "data_bucket" {
  value = aws_s3_bucket.data.id
}

output "frontend_bucket" {
  description = "Target for infra/aws/deploy_frontend.sh."
  value       = aws_s3_bucket.frontend.id
}
