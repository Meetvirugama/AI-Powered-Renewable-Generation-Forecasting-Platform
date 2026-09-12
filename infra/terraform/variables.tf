variable "region" {
  description = "AWS region. Mumbai: lowest latency for judges in India."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "renewable"
}

variable "instance_type" {
  description = <<-EOT
    Backend instance size. t3.large (8 GB) is the floor: bge-m3 is ~2.2 GB
    resident, the reranker adds ~300 MB, and two uvicorn workers sit on top.
    t3.medium OOM-kills the container under any real load.
  EOT
  type        = string
  default     = "t3.large"
}

variable "db_instance_class" {
  description = "RDS size. The corpus is ~2k rows; this is not the bottleneck."
  type        = string
  default     = "db.t4g.micro"
}

variable "root_volume_gb" {
  description = "Root volume. The image alone is ~4.5 GB and Docker keeps the previous one."
  type        = number
  default     = 40
}

variable "bucket_suffix" {
  description = "Suffix that makes the S3 bucket names globally unique."
  type        = string
}
