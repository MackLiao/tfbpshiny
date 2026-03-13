variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-2"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "Name of the EC2 key pair for SSH access (must already exist in the target region)"
  type        = string
}

variable "root_volume_gb" {
  description = "Root EBS volume size in GB (minimum 12 recommended; 20 provides room for Docker images and HF cache)"
  type        = number
  default     = 20
}
