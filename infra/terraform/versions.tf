terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment after creating the bucket and lock table (see README.md).
  # State holds the RDS master password in plaintext, so it lives in a
  # versioned, encrypted bucket and never in git.
  #
  # backend "s3" {
  #   bucket         = "renewable-tfstate-<suffix>"
  #   key            = "platform/terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "renewable-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Sprint    = "hackout-2026"
    }
  }
}
