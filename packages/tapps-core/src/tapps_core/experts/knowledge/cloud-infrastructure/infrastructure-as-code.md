# Infrastructure as Code (IaC)

## Overview

Infrastructure as Code (IaC) manages infrastructure through machine-readable definition files rather than manual configuration. This enables version control, repeatability, and automation.

## Benefits

- **Version Control:** Track infrastructure changes
- **Reproducibility:** Consistent environments
- **Automation:** Reduce manual errors
- **Collaboration:** Teams work on infrastructure code
- **Testing:** Test infrastructure changes

## Tools

### Terraform / OpenTofu

> **Important licensing note (2024+):** HashiCorp changed Terraform to BSL (Business Source License) in August 2023. **OpenTofu** is the community-maintained MPL-licensed fork. Both share the same HCL syntax and provider ecosystem. Choose based on licensing needs.

**Declarative IaC (syntax works for both Terraform and OpenTofu):**
```hcl
provider "aws" {
  region = "us-west-2"
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"

  tags = {
    Name = "WebServer"
  }
}

output "instance_ip" {
  value = aws_instance.web.public_ip
}
```

**Terraform (HashiCorp) - BSL Licensed:**
- Multi-cloud support, state management, plan/apply workflow, modules
- Focus shifting to HCP (HashiCorp Cloud Platform) AI Ecosystem
- Terraform Stacks GA for multi-deployment orchestration
- Project Infragraph for infrastructure visualization
- Paid features increasingly tied to HCP

**OpenTofu v1.11 (Dec 2025) - MPL Open-Source:**
- Drop-in replacement for Terraform (same HCL syntax, same providers)
- **Native state encryption** (since v1.7, refined in v1.11) - encrypts state files at rest without external tools
- **Ephemeral values** - sensitive values that exist only during plan/apply, never written to state
- **Conditional resources** - `count` and `for_each` with improved conditional logic
- Maintains MPL open-source commitment under Linux Foundation
- Growing provider and module ecosystem parity

**Key decision factor:** If open-source licensing matters (compliance, redistribution, avoiding vendor lock-in), use OpenTofu. If you need HCP integrations or commercial support from HashiCorp, use Terraform.

### CloudFormation (AWS)

**AWS Native:**
```yaml
Resources:
  WebServer:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-0c55b159cbfafe1f0
      InstanceType: t3.micro
      Tags:
        - Key: Name
          Value: WebServer

Outputs:
  InstanceIP:
    Value: !GetAtt WebServer.PublicIp
```

### Pulumi

**Code in Your Language:**
```python
import pulumi
import pulumi_aws as aws

instance = aws.ec2.Instance("web",
    ami="ami-0c55b159cbfafe1f0",
    instance_type="t3.micro",
    tags={
        "Name": "WebServer"
    }
)

pulumi.export("instance_ip", instance.public_ip)
```

## Best Practices

### 1. Modularity

**Reusable Modules:**
```hcl
module "vpc" {
  source = "./modules/vpc"
  cidr   = "10.0.0.0/16"
}

module "web_server" {
  source = "./modules/web_server"
  vpc_id = module.vpc.id
}
```

### 2. State Management

**Remote State:**
```hcl
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-west-2"
  }
}
```

### 3. Environment Management

**Separate Environments:**
```
environments/
  dev/
    terraform.tfvars
  staging/
    terraform.tfvars
  production/
    terraform.tfvars
```

### 4. Variable Management

**Use Variables:**
```hcl
variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

resource "aws_instance" "web" {
  instance_type = var.instance_type
}
```

### 5. Outputs

**Expose Important Values:**
```hcl
output "database_endpoint" {
  value       = aws_db_instance.main.endpoint
  description = "Database connection endpoint"
}
```

## Patterns

### DRY (Don't Repeat Yourself)

**Use Modules:**
- Create reusable modules
- Parameterize modules
- Compose modules

### Immutable Infrastructure

**Replace Don't Modify:**
- Create new instances
- Test new infrastructure
- Switch traffic
- Destroy old infrastructure

### GitOps

**Infrastructure in Git:**
- Store IaC in Git
- Review changes via PR
- Automate deployment
- Rollback via Git

## Best Practices Summary

1. **Version control** all infrastructure code
2. **Use modules** for reusability
3. **Manage state** remotely and securely
4. **Separate environments** (dev, staging, prod)
5. **Use variables** for flexibility
6. **Document** infrastructure code
7. **Test** infrastructure changes
8. **Review** changes before applying
9. **Automate** deployments via CI/CD
10. **Monitor** infrastructure changes

